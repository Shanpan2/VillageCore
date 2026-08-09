import asyncio
import tempfile
import unittest
from pathlib import Path

from database import config_db


def run(coro):
    return asyncio.run(coro)


class CoinTransferTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        config_db.DATABASE_URL = None
        config_db.DB_PATH = str(Path(self.temp_dir.name) / "coins.db")
        run(config_db.db_init())

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_transfer_moves_balance_atomically(self):
        run(config_db.db_set("sender", "100"))
        run(config_db.db_set("recipient", "25"))

        result = run(config_db.db_transfer_int("sender", "recipient", 40))

        self.assertEqual(result, (True, 60, 65))
        self.assertEqual(run(config_db.db_get("sender")), "60")
        self.assertEqual(run(config_db.db_get("recipient")), "65")

    def test_transfer_rejects_insufficient_balance_without_changes(self):
        run(config_db.db_set("sender", "10"))
        run(config_db.db_set("recipient", "25"))

        result = run(config_db.db_transfer_int("sender", "recipient", 11))

        self.assertEqual(result, (False, 10, 25))
        self.assertEqual(run(config_db.db_get("sender")), "10")
        self.assertEqual(run(config_db.db_get("recipient")), "25")

    def test_transfer_rejects_non_positive_amount(self):
        for amount in (0, -1):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                run(config_db.db_transfer_int("sender", "recipient", amount))

    def test_transfer_rejects_same_key(self):
        with self.assertRaises(ValueError):
            run(config_db.db_transfer_int("sender", "sender", 1))


if __name__ == "__main__":
    unittest.main()
