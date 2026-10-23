import re
import unittest

from models.postgres_compat import translate_mysql_sql


class PostgresCreateTableTranslationTests(unittest.TestCase):
    def test_inline_index_removal_preserves_foreign_key_separator(self):
        statement = """
            CREATE TABLE IF NOT EXISTS resort_photos (
                photo_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                resort_id INT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_resort_photos_resort (resort_id),
                CONSTRAINT fk_resort_photos_resort
                    FOREIGN KEY (resort_id) REFERENCES resorts(resort_id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """

        translated, table, indexes = translate_mysql_sql(statement)

        self.assertEqual(table, "resort_photos")
        self.assertEqual(indexes, [("idx_resort_photos_resort", "resort_id")])
        self.assertRegex(translated, re.compile(r"CURRENT_TIMESTAMP\s*,\s*CONSTRAINT"))

    def test_inline_index_at_end_does_not_leave_trailing_comma(self):
        statement = """
            CREATE TABLE IF NOT EXISTS resort_updates (
                update_id INT AUTO_INCREMENT PRIMARY KEY,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_resort_updates_created (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """

        translated, table, indexes = translate_mysql_sql(statement)

        self.assertEqual(table, "resort_updates")
        self.assertEqual(indexes, [("idx_resort_updates_created", "created_at")])
        self.assertRegex(translated, re.compile(r"CURRENT_TIMESTAMP\s*\)"))


if __name__ == "__main__":
    unittest.main()
