import re
from io import BytesIO

import pytest
from PIL import Image

from sportive import create_app
from sportive.db import get_db


@pytest.fixture
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "test.db"),
        "SECRET_KEY": "test",
        "CSRF_ENABLED": False,
        "PASSWORD_HASH_METHOD": "pbkdf2:sha256:1000",  # fast hashing for tests only
        # Games in tests start "tomorrow at this time", whatever time the tests run: opening hours have their own
        # tests (they turn this back on), so the rest don't fail at night.
        "CHECK_PLACE_HOURS": False,
    })


@pytest.fixture
def client(app):
    return app.test_client()


class Accounts:
    """Helpers to sign up / log in test users."""

    def __init__(self, app, client):
        self.app, self.client = app, client

    def signup(self, email="dubs@uw.edu", password="purple-and-gold", name="Dubs Husky",
               sports=("basketball",), birth_date="2005-01-15", verify=True, photo=True):
        response = self.client.post("/signup", data={
            "full_name": name, "email": email, "password": password, "password2": password,
            "birth_date": birth_date, "grad_year": "2028",
        })
        if response.status_code == 302 and response.headers["Location"].split("?")[0] == "/signup":
            response = self.client.get(response.headers["Location"])   # a problem: shown on the sign-up page
        elif response.status_code == 302:  # step 2: sports
            self.client.post("/signup/sports", data={"sports": list(sports)})
        if verify:
            self.client.post("/verify", data={"code": self.code_for(email)})
            if photo:
                self.upload_photo()
        return response

    def upload_photo(self, data=None, filename="me.png"):
        return self.client.post("/profile/photo", data={"photo": (BytesIO(data or make_image()), filename)},
                                content_type="multipart/form-data")

    def code_for(self, email):
        with self.app.app_context():
            return get_db().execute("SELECT verify_code FROM users WHERE email = ?", (email,)).fetchone()[0]

    def login(self, email="dubs@uw.edu", password="purple-and-gold"):
        return self.client.post("/login", data={"email": email, "password": password})

    def logout(self):
        return self.client.post("/logout")


def make_image(size=(400, 300), fmt="PNG", exif=None):
    output = BytesIO()
    image = Image.new("RGB", size, "purple")
    if exif is not None:
        image.save(output, fmt, exif=exif)
    else:
        image.save(output, fmt)
    return output.getvalue()


@pytest.fixture
def accounts(app, client):
    return Accounts(app, client)


def event_id_from(response):
    return int(re.search(r"/events/(\d+)", response.headers["Location"]).group(1))
