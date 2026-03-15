from locust import HttpUser, task, between


class DashUser(HttpUser):
    wait_time = between(1, 3) # пауза между действиями от 1 до 3 секунд

    @task                   #действие пользователя
    def open_dashboard(self):
        self.client.get("/")     #запрос к главной странице