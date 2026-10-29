from locust import HttpUser, task, between


class ApiUser(HttpUser):
    wait_time = between(0.1, 0.5)

    @task(3)
    def health(self):
        self.client.get("/health")

    @task(2)
    def list_items(self):
        self.client.get("/items")
