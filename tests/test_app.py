import unittest
from src import app


class TestApp(unittest.TestCase):
    def test_add_positive(self):
        self.assertEqual(app.add(2, 3), 5)

    def test_add_negative(self):
        self.assertEqual(app.add(-1, -1), -2)

    def test_multiply_positive(self):
        self.assertEqual(app.multiply(3, 4), 12)

    def test_multiply_by_zero(self):
        self.assertEqual(app.multiply(5, 0), 0)


if __name__ == "__main__":
    unittest.main()

