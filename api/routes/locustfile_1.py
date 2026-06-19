from locust import HttpUser, TaskSet, task, between, events
from locust import constant_pacing, LoadTestShape
import random
import time
import json

# Configuration
STREAMLIT_BASE = "/"  # adjust if streamlit served under a path
API_BASE = "/api"  # base for API endpoints

# Helper utilities

def random_sleep(min_s=0.5, max_s=2.0):
    time.sleep(random.uniform(min_s, max_s))


class UserBehavior(TaskSet):
    def on_start(self):
        # Simulate anonymous/free signup/login (if API exists)
        try:
            with self.client.post(f"{API_BASE}/auth/register", json={"username": f"bot_{random.randint(10000,99999)}", "password": "botpass"}, catch_response=True) as r:
                if r.status_code in (200, 201):
                    self.token = r.json().get("access_token")
                else:
                    # fallback: try login if register not allowed
                    self.token = None
        except Exception:
            self.token = None

    @task(3)
    def view_streamlit_index(self):
        # Hit the streamlit index page
        self.client.get(STREAMLIT_BASE, name="streamlit_index")
        random_sleep(0.1, 0.5)

    @task(5)
    def view_map_tiles_and_api(self):
        # Simulate loading map and backend tiles
        # Frontend may call endpoints for tiles or geojson
        self.client.get(f"{API_BASE}/map/lands?bbox=0,0,10,10", name="api_map_lands")
        self.client.get(f"{API_BASE}/map/land/summary?id={random.randint(1,1000)}", name="api_map_land_summary")
        random_sleep(0.05, 0.2)

    @task(2)
    def request_seven_dim_report(self):
        # Request a heavy report: 7-dimensional land feasibility
        payload = {"land_id": random.randint(1, 1000), "details_level": "full"}
        headers = {}
        if getattr(self, 'token', None):
            headers['Authorization'] = f"Bearer {self.token}"
        with self.client.post(f"{API_BASE}/reports/seven_dim", json=payload, headers=headers, name="api_reports_seven_dim", catch_response=True) as r:
            # If server returns 202 for async processing, also poll the status endpoint
            if r.status_code == 202:
                try:
                    job = r.json().get('job_id')
                    if job:
                        # Poll job status quickly
                        for _ in range(3):
                            self.client.get(f"{API_BASE}/reports/status/{job}", name="api_reports_status")
                            random_sleep(0.1, 0.5)
                except Exception:
                    pass
            elif r.status_code >= 500:
                r.failure(f"Server error: {r.status_code}")

    @task(1)
    def random_non_critical(self):
        # Search lands, open user profile
        q = random.choice(["alley", "river", "farm", "zone"]) 
        self.client.get(f"{API_BASE}/lands/search?q={q}", name="api_search_lands")
        random_sleep(0.05, 0.2)


class WebsiteUser(HttpUser):
    tasks = [UserBehavior]
    wait_time = between(0.5, 2)
    host = "http://localhost:8501"  # default Streamlit + API origin; modify as needed


# Load shape: ramp from 20 to 100 users over 60 seconds
class RampShape(LoadTestShape):
    start_users = 20
    target_users = 100
    ramp_time = 60  # seconds to reach target

    def tick(self):
        run_time = self.get_run_time()
        if run_time > self.ramp_time:
            return (self.target_users, 1)
        # linear ramp
        users = int(self.start_users + (self.target_users - self.start_users) * (run_time / self.ramp_time))
        spawn_rate = max(1, int((users - self.start_users) / max(1, run_time)))
        return (users, spawn_rate)


# Event hook to record errors and other metrics
@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    stats = environment.runner.stats
    # export a small JSON report
    report = {
        'total_requests': stats.total.num_requests,
        'total_failures': stats.total.num_failures,
        'avg_response_time_ms': stats.total.avg_response_time,
        'fail_ratio': (stats.total.num_failures / stats.total.num_requests) if stats.total.num_requests else 0,
    }
    try:
        with open('locust_test_summary.json', 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
