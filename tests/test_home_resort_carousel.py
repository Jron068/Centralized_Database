import unittest
from unittest.mock import patch

from app import app
import routes.public.home as public_home


class _Cursor:
    def __init__(self, resorts):
        self.resorts = resorts
        self.query = ""

    def execute(self, query, params=None):
        self.query = query

    def fetchall(self):
        return self.resorts

    def close(self):
        pass


class HomeResortCarouselTests(unittest.TestCase):
    def test_homepage_carousel_includes_all_registered_resorts(self):
        resorts = [
            {
                "resort_id": 1,
                "resort_name": "Active Resort",
                "status": "Active",
                "price": None,
                "max_pax": None,
                "photos": [],
            },
            {
                "resort_id": 2,
                "resort_name": "Inactive Resort",
                "status": "Inactive",
                "price": None,
                "max_pax": None,
                "photos": [],
            },
        ]
        cursor = _Cursor(resorts)
        connection = type(
            "Connection",
            (),
            {"cursor": lambda self, dictionary=False: cursor, "close": lambda self: None},
        )()

        with patch.object(public_home, "get_connection", return_value=connection):
            with patch.object(public_home, "enrich_resorts", side_effect=lambda rows: rows):
                with patch.object(public_home, "get_resort_photos", return_value={}):
                    with patch.object(public_home, "gallery_photos", return_value=[]):
                        response = app.test_client().get("/")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("WHERE status = 'Active'", cursor.query)
        self.assertIn(b"Active Resort", response.data)
        self.assertIn(b"Inactive Resort", response.data)
        self.assertIn(b"Currently unavailable for booking", response.data)
        self.assertEqual(response.data.count(b"<article class=\"resort-hero-slide"), 2)
        self.assertIn(b"data-resort-next", response.data)
        self.assertIn(b"Explore &amp; book", response.data)


if __name__ == "__main__":
    unittest.main()
