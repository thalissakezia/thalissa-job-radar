import unittest

from radar.models import Job, normalize_currency
from radar.scoring import evaluate
from radar.sources import _extract_brl_salary, _jobspy_row_to_job


RJ = ["rio de janeiro", "nova iguaçu", "mesquita"]


class RadarTests(unittest.TestCase):
    def test_remote_power_bi_is_priority(self):
        job = Job(
            source="test",
            external_id="1",
            title="Analista de Dados - Power BI",
            company="Empresa",
            location="Brasil",
            url="https://example.com/1",
            description="Excel, dashboards e indicadores",
            work_mode="remoto",
        )
        match = evaluate(job, RJ)
        self.assertFalse(match.rejected)
        self.assertGreaterEqual(match.score, 10)
        self.assertEqual(match.label, "PRIORIDADE")

    def test_remote_english_value_is_supported(self):
        job = Job(
            source="test",
            external_id="11",
            title="Analista de Dados",
            company="Empresa",
            location="Brazil",
            url="https://example.com/11",
            work_mode="remote",
        )
        self.assertFalse(evaluate(job, RJ).rejected)

    def test_brl_is_normalized(self):
        self.assertEqual(normalize_currency("R$"), "BRL")
        self.assertEqual(normalize_currency("BRL"), "BRL")

    def test_salary_parser_requires_salary_context(self):
        low, high, period = _extract_brl_salary(
            "Remuneração: R$ 3.500,00 a R$ 4.500,00 por mês"
        )
        self.assertEqual(low, 3500.0)
        self.assertEqual(high, 4500.0)
        self.assertEqual(period, "monthly")

        self.assertEqual(
            _extract_brl_salary("Vale alimentação de R$ 600,00"),
            (None, None, None),
        )

    def test_jobspy_maps_remote_and_brl(self):
        job = _jobspy_row_to_job(
            {
                "id": "li-123",
                "site": "linkedin",
                "title": "Analista de Dados Jr",
                "company": "Empresa",
                "job_url": "https://linkedin.com/jobs/view/123",
                "job_url_direct": "https://empresa.com/vaga/123",
                "location": "Brazil",
                "date_posted": "2026-10-07",
                "is_remote": True,
                "min_amount": 4000,
                "max_amount": 5000,
                "currency": "BRL",
                "interval": "monthly",
                "description": "Power BI e Excel",
            },
            easy_apply_requested=True,
        )
        self.assertIsNotNone(job)
        self.assertEqual(job.work_mode, "remoto")
        self.assertEqual(job.salary_currency, "BRL")
        self.assertTrue(job.easy_apply)
        self.assertEqual(job.direct_url, "https://empresa.com/vaga/123")

    def test_senior_title_is_rejected(self):
        job = Job(
            source="test",
            external_id="2",
            title="Senior Data Analyst",
            company="Empresa",
            location="Remote",
            url="https://example.com/2",
        )
        self.assertTrue(evaluate(job, RJ).rejected)

    def test_onsite_outside_rj_is_rejected(self):
        job = Job(
            source="test",
            external_id="3",
            title="Assistente Administrativo",
            company="Empresa",
            location="São Paulo, SP",
            url="https://example.com/3",
            work_mode="onsite",
        )
        self.assertTrue(evaluate(job, RJ).rejected)


if __name__ == "__main__":
    unittest.main()
