import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from models import file_storage


class _Response:
    def __init__(self, body=b"{}", status=200):
        self.body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]


class FileStorageTests(unittest.TestCase):
    def setUp(self):
        file_storage._signed_url_cache.clear()

    def test_upload_uses_public_bucket_and_returns_stable_reference(self):
        environment = {
            "SUPABASE_URL": "https://project.supabase.co",
            "SUPABASE_STORAGE_SERVICE_ROLE_KEY": "test-key",
            "FLASK_DEBUG": "0",
        }
        with patch.dict(os.environ, environment, clear=True):
            with patch.object(file_storage, "urlopen", return_value=_Response()) as send:
                reference = file_storage.upload_file(
                    b"image", "resort_photos/1/photo.png", content_type="image/png"
                )

        self.assertEqual(reference, "supabase://resort-media/resort_photos/1/photo.png")
        self.assertEqual(send.call_args.args[0].get_method(), "POST")

    def test_private_file_url_is_signed_and_cached(self):
        environment = {
            "SUPABASE_URL": "https://project.supabase.co",
            "SUPABASE_STORAGE_SERVICE_ROLE_KEY": "test-key",
            "FLASK_DEBUG": "0",
        }
        signed = _Response(
            json.dumps({"signedURL": "/object/sign/payment-proofs/payments/proof.png?token=x"}).encode()
        )
        with app.app.test_request_context():
            with patch.dict(os.environ, environment, clear=True):
                with patch.object(file_storage, "urlopen", return_value=signed) as send:
                    first_url = file_storage.file_url(
                        "supabase://payment-proofs/payments/proof.png"
                    )
                    second_url = file_storage.file_url(
                        "supabase://payment-proofs/payments/proof.png"
                    )

        self.assertEqual(first_url, second_url)
        self.assertTrue(first_url.endswith("/storage/v1/object/sign/payment-proofs/payments/proof.png?token=x"))
        send.assert_called_once()

    def test_production_upload_requires_storage_configuration(self):
        with app.app.app_context():
            with patch.dict(os.environ, {"FLASK_DEBUG": "0"}, clear=True):
                with self.assertRaises(file_storage.FileStorageError):
                    file_storage.upload_file(b"image", "profiles/photo.png")

    def test_debug_upload_falls_back_to_local_static_storage(self):
        with app.app.app_context():
            with patch.dict(os.environ, {"FLASK_DEBUG": "1"}, clear=True):
                reference = file_storage.upload_file(b"local-test", "tests/storage-check.txt")
                path = Path(app.app.static_folder) / reference
                try:
                    self.assertEqual(path.read_bytes(), b"local-test")
                finally:
                    file_storage.delete_uploaded_file(reference)
                self.assertFalse(path.exists())

    def test_verification_get_redirects_to_otp_for_pending_registration(self):
        with app.app.test_client() as client:
            with client.session_transaction() as session:
                session["otp_email"] = "user@example.test"

            response = client.get("/verification")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/otp")

    def test_verification_get_without_pending_registration_redirects_to_signup(self):
        response = app.app.test_client().get("/verification")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/registration")


if __name__ == "__main__":
    unittest.main()
