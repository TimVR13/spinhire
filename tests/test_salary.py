import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.salary import format_salary, parse_salary

# Тысячи разделяются неразрывным пробелом — так вилка не рвётся при переносе


class SalaryParsingTests(unittest.TestCase):
    def assert_salary(self, text, expected):
        self.assertEqual(format_salary(parse_salary(text)), expected, text[:60])

    def test_annual_range_in_dollars(self):
        self.assert_salary(
            "The salary for this role is based on an annualized range of "
            "$85,000 - $110,000 USD.", "$85\u00a0000–110\u00a0000 в год")

    def test_monthly_range_in_euro(self):
        self.assert_salary("Gross monthly salary from 1070 EUR to 2680 EUR",
                           "€1\u00a0070–2\u00a0680")

    def test_hourly_rate_keeps_cents(self):
        self.assert_salary("Competitive salary: $18.25 – $24.00/hour",
                           "$18,25–24 в час")

    def test_currency_only_on_upper_bound(self):
        self.assert_salary("Зарплата от 1200 до 1800 EUR на руки", "€1\u00a0200–1\u00a0800")

    def test_single_amount(self):
        self.assert_salary("This role offers an annualized salary of up to "
                           "$350,000 USD", "$350\u00a0000 в год")

    # --- то, что зарплатой не является ---

    def test_wellness_allowance_is_not_salary(self):
        self.assert_salary("• €300 yearly wellness allowance. • Office perks", "")

    def test_referral_bonus_is_not_salary(self):
        self.assert_salary("Реферальная программа с бонусом €1 000 за друга", "")

    def test_training_budget_is_not_salary(self):
        self.assert_salary("Мы даём бюджет на обучение €2 000 в год", "")

    def test_amount_without_pay_word_is_ignored(self):
        self.assert_salary("Наши клиенты выигрывают до €50 000 за вечер", "")

    def test_phone_number_is_not_salary(self):
        self.assert_salary("Зарплата обсуждается, звоните 380 67 123 45 67", "")

    def test_ambiguous_magnitude_is_dropped(self):
        """14 400–18 000 без пометки периода: месяц или год — непонятно.

        Лучше отдать вакансию без вилки, чем показать годовой оклад месячным.
        """
        self.assert_salary("Salary for this role can range between "
                           "€14,400 - 18,000+ (including performance bonuses)", "")

    def test_empty_input(self):
        self.assertIsNone(parse_salary(""))
        self.assertIsNone(parse_salary(None))
        self.assertEqual(format_salary(None), "")


if __name__ == "__main__":
    unittest.main()
