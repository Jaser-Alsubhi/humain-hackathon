"""Add the 'break it live' panel to site/index.html. Safe to run again after every rebuild of the page.
python scripts/add_live_to_site.py"""
import re
from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "site" / "index.html"

CSS = """/*LIVE-CSS*/
.modes{display:flex;gap:6px;padding:10px 14px 0}
.modes button{border:1px solid #B9C1C9;background:transparent;border-radius:99px;padding:6px 14px;font-weight:600;font-size:14px}
.modes button[aria-selected=true]{background:var(--ink);color:#fff;border-color:var(--ink)}
.modes button:disabled{opacity:.5;cursor:default}
.bar[hidden]{display:none}
.livenote{padding:0 16px 10px;color:var(--muted);font-size:14px}
ol.steps li.info{font-family:"Bricolage Grotesque",system-ui,sans-serif;font-size:14px;color:var(--muted)}
.btn:disabled{opacity:.55;cursor:default}
/*END-LIVE-CSS*/
"""

MARKUP = """<!--LIVE-MARKUP--><div class="modes" id="modes" role="tablist" aria-label="Mode"><button data-mode="live" role="tab" aria-selected="false" hidden>Break it live</button><button data-mode="replay" role="tab" aria-selected="true">Recorded replay</button></div>
    <div class="bar" id="livebar" hidden><select id="lsc" aria-label="Choose a fault to inject"></select><button class="btn" id="lbreak">Break it</button></div>
    <!--END-LIVE-MARKUP-->
    """

JS = r"""/*LIVE-JS*/
(function(){
  var modes=document.querySelectorAll("#modes button"),rbar=document.getElementById("sc").parentNode,lbar=document.getElementById("livebar");
  var lsel=document.getElementById("lsc"),lbtn=document.getElementById("lbreak"),ol=document.getElementById("steps");
  var live=false,since=0,pollT=null,available=false,busy=false,labels={};
  function show(m){
    live=(m==="live");
    modes.forEach(function(b){b.setAttribute("aria-selected",b.dataset.mode===m?"true":"false")});
    rbar.hidden=live;lbar.hidden=!live;
    clearTimeout(pollT);
    if(live){since=0;idle()}else{reset()}
  }
  function idle(){
    setState("up","Healthy","waiting for you");
    document.getElementById("alert").textContent="Pick a fault and press Break it. The monitor is not told what you chose.";
    ol.innerHTML='<li class="on empty" style="font-family:inherit;opacity:1">This is the real stack running on the server, not a recording.</li>';
    document.getElementById("ticketbox").innerHTML="";
    document.getElementById("meta").textContent="Live runs are limited so everyone gets a turn. One break per visit is plenty.";
    lbtn.disabled=false;
    poll(true);
  }
  var DOES=ACT.concat(["restore_sync_job","resync_ledger"]);
  function tag(t){var nm=t.split("(")[0],a=DOES.indexOf(nm)>-1,e=nm==="escalate";return e?'<span class="t esc">hands off</span>':(a?'<span class="t act">changes system</span>':'<span class="t">reads</span>')}
  function line(txt){
    var m=/^\s*\d+\.\s+([a-z_]+)\((.*?)\)\s+->\s+(.*)$/.exec(txt);
    if(m){return '<li class="on"><span>'+esc(m[1]+" "+m[3].slice(0,90))+'</span>'+tag(m[1]+"(")+'</li>'}
    return '<li class="on info"><span>'+esc(txt.replace(/^\[\d\d:\d\d:\d\d\]\s*/,""))+'</span></li>'
  }
  function react(txt){
    if(/check failing/.test(txt))setState("down","Failing","the monitor noticed on its own");
    else if(/incident detected/.test(txt))setState("work","Agent working");
    else if(/agent finished: recovered=True/.test(txt))setState("up","Recovered, verified");
    else if(/handed over to a human/.test(txt))setState("hand","Handed to a human","ticket written");
    else if(/Fault injected/.test(txt))setState("up","Fault injected","waiting for the monitor");
  }
  function poll(once){
    fetch("/api/live/status?since="+since,{cache:"no-store"}).then(function(r){return r.json()}).then(function(s){
      if(!live)return;
      if(once===true&&s.state!=="running"){lbtn.disabled=!s.enabled||s.runs_left<1||s.wait>0;return}
      if(since===0&&s.events.length)ol.innerHTML="";
      s.events.forEach(function(e){ol.insertAdjacentHTML("beforeend",line(e.text));react(e.text)});
      ol.scrollTop=ol.scrollHeight;since=s.next;
      busy=s.state==="running";
      lbtn.disabled=busy||!s.enabled||s.runs_left<1;
      if(busy){document.getElementById("alert").textContent="Live run: "+(labels[s.scenario]||s.scenario);}
      if(s.state==="done"&&!busy){
        setState(s.recovered?"up":"down",s.recovered?"Recovered, verified":"Not recovered");
        document.getElementById("meta").textContent="Took "+Math.round(s.seconds)+" s with nobody pressing anything. "+s.runs_left+" live runs left today.";
        lbtn.disabled=s.wait>0||s.runs_left<1;
        if(s.wait>0)setTimeout(function(){lbtn.disabled=false},s.wait*1000);
        return;
      }
      if(busy||s.state==="done")pollT=setTimeout(poll,1500);
    }).catch(function(){
      if(live){document.getElementById("meta").textContent="Live mode is offline right now. The recorded replay works.";lbtn.disabled=true}
    });
  }
  lbtn.addEventListener("click",function(){
    lbtn.disabled=true;since=0;ol.innerHTML="";
    fetch("/api/live/break",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({scenario:lsel.value})})
      .then(function(r){return r.json().then(function(j){return [r.status,j]})})
      .then(function(x){
        if(x[0]===200){setState("up","Healthy","breaking it now");poll()}
        else{document.getElementById("meta").textContent=x[1].message||x[1].error||"Could not start.";lbtn.disabled=false;if(x[0]===409){since=0;poll()}}
      }).catch(function(){document.getElementById("meta").textContent="Live mode is offline right now.";lbtn.disabled=false});
  });
  modes.forEach(function(b){b.addEventListener("click",function(){show(b.dataset.mode)})});
  fetch("/api/live/scenarios",{cache:"no-store"}).then(function(r){if(!r.ok)throw 0;return r.json()}).then(function(j){
    if(!j.enabled)return;
    j.scenarios.forEach(function(s){labels[s.id]=s.label});
    lsel.innerHTML=j.scenarios.map(function(s){return '<option value="'+s.id+'">'+esc(s.label)+'</option>'}).join("");
    modes[0].hidden=false;available=true;document.getElementById("cta-play").textContent="Break it yourself";show("live");
  }).catch(function(){});
  document.getElementById("cta-play").addEventListener("click",function(e){
    if(!available)return;
    e.stopImmediatePropagation();if(!live)show("live");
    document.querySelector(".console").scrollIntoView({behavior:"smooth",block:"center"});
  },true);
})();
/*END-LIVE-JS*/
"""


def strip(html):
    html = re.sub(r"/\*LIVE-CSS\*/.*?/\*END-LIVE-CSS\*/\n?", "", html, flags=re.S)
    html = re.sub(r"<!--LIVE-MARKUP-->.*?<!--END-LIVE-MARKUP-->\s*", "", html, flags=re.S)
    html = html.replace('<div class="bar" id="replaybar"><select id="sc"', '<div class="bar"><select id="sc"')
    return re.sub(r"/\*LIVE-JS\*/.*?/\*END-LIVE-JS\*/\n?", "", html, flags=re.S)


def patch(html):
    html = strip(html)
    for old, new in (("</style>", CSS + "</style>"),
                     ('<div class="bar"><select id="sc"', MARKUP + '<div class="bar" id="replaybar"><select id="sc"'),
                     ("reset();\n</script>", "reset();\n" + JS + "</script>")):
        assert html.count(old) == 1, "cannot find " + old[:40]
        html = html.replace(old, new)
    return html


if __name__ == "__main__":
    PAGE.write_text(patch(PAGE.read_text(encoding="utf-8")), encoding="utf-8")
    print("live panel added to", PAGE)
