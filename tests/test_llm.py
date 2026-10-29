from pydantic import BaseModel
from src.llm import ask_json


class Answer(BaseModel):
    answer: str


def test_mock_json():
    assert ask_json("hi", Answer).answer == "mock"
