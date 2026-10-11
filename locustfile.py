from uuid import uuid4

from locust import HttpUser, between, task


class MusicClient(HttpUser):
    wait_time = between(0.02, 0.2)

    @task(8)
    def submit_play(self):
        self.client.post(
            "/v1/events",
            json={
                "event_type": "play",
                "user_id": self.user_id,
                "track_id": f"track-{int(self.user_id[-4:], 16) % 500}",
            },
            name="/v1/events",
        )

    @task(2)
    def request_recommendations(self):
        self.client.get(
            "/v1/recommendations",
            params={"user_id": self.user_id},
            name="/v1/recommendations",
        )

    def on_start(self):
        self.user_id = f"load-user-{uuid4().hex}"
        self.client.get("/health/ready", name="/health/ready")
