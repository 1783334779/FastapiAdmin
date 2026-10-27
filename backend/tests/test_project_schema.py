"""项目输入校验的独立测试，不启动应用、不加载数据库初始化。

单独运行：backend/.venv/bin/python -B backend/tests/test_project_schema.py
"""

import json
import runpy
import unittest
from datetime import date
from pathlib import Path

from pydantic import ValidationError

# 直接执行独立 Schema 文件，避免导入 app 包及其配置、日志等应用依赖。
_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "app/modules/business/project/schema.py"
ProjectCreateSchema = runpy.run_path(str(_SCHEMA_PATH))["ProjectCreateSchema"]


def valid_payload() -> dict:
    """ID 和字典值仅是格式测试数据，不表示数据库存在这些记录。"""
    return {
        "name": "后端学习项目",
        "initiation_type": "test_initiation",
        "category": "test_category",
        "it_manager_ids": [11, 12],
        "external_purchase": False,
        "business_manager_ids": [21, 22],
        "business_dept_id": 31,
        "planned_start_date": "2026-11-01",
        "planned_end_date": "2027-04-30",
        "currency": "test_currency",
    }


class TestProjectCreateSchema(unittest.TestCase):
    def test_valid_input_and_false_purchase_are_accepted(self) -> None:
        project = ProjectCreateSchema.model_validate(valid_payload())
        self.assertIs(project.external_purchase, False)
        self.assertEqual(project.planned_start_date, date(2026, 11, 1))
        self.assertEqual(project.it_manager_ids, [11, 12])

    def test_every_field_is_required(self) -> None:
        for field in valid_payload():
            with self.subTest(field=field):
                payload = valid_payload()
                del payload[field]
                with self.assertRaises(ValidationError) as error:
                    ProjectCreateSchema.model_validate(payload)
                self.assertEqual(error.exception.errors()[0]["loc"], (field,))

    def test_null_is_rejected_for_every_field(self) -> None:
        for field in valid_payload():
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    ProjectCreateSchema.model_validate({**valid_payload(), field: None})

    def test_text_is_trimmed(self) -> None:
        payload = valid_payload()
        for field in ("name", "initiation_type", "category", "currency"):
            payload[field] = f"  {payload[field]}  "
        project = ProjectCreateSchema.model_validate(payload)
        for field in ("name", "initiation_type", "category", "currency"):
            self.assertEqual(getattr(project, field), valid_payload()[field])

    def test_blank_text_is_rejected(self) -> None:
        for field in ("name", "initiation_type", "category", "currency"):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    ProjectCreateSchema.model_validate({**valid_payload(), field: " \t "})

    def test_text_length_limits(self) -> None:
        for field, limit in (("name", 200), ("initiation_type", 255), ("category", 255), ("currency", 255)):
            with self.subTest(field=field):
                ProjectCreateSchema.model_validate({**valid_payload(), field: "字" * limit})
                with self.assertRaises(ValidationError):
                    ProjectCreateSchema.model_validate({**valid_payload(), field: "字" * (limit + 1)})

    def test_empty_manager_lists_are_rejected(self) -> None:
        for field in ("it_manager_ids", "business_manager_ids"):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    ProjectCreateSchema.model_validate({**valid_payload(), field: []})

    def test_invalid_manager_ids_are_rejected(self) -> None:
        for field in ("it_manager_ids", "business_manager_ids"):
            for value in (0, -1, True, "11", 1.5, None):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValidationError):
                        ProjectCreateSchema.model_validate({**valid_payload(), field: [value]})

    def test_manager_lists_are_deduplicated_independently(self) -> None:
        project = ProjectCreateSchema.model_validate(
            {
                **valid_payload(),
                "it_manager_ids": [12, 11, 12],
                "business_manager_ids": [12, 21, 12],
            }
        )
        self.assertEqual(project.it_manager_ids, [12, 11])
        self.assertEqual(project.business_manager_ids, [12, 21])

    def test_invalid_department_ids_are_rejected(self) -> None:
        for value in (0, -1, True, "31", 1.5):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    ProjectCreateSchema.model_validate({**valid_payload(), "business_dept_id": value})

    def test_purchase_requires_a_real_boolean(self) -> None:
        ProjectCreateSchema.model_validate({**valid_payload(), "external_purchase": True})
        for value in (0, 1, "true", "false", "是", "否"):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    ProjectCreateSchema.model_validate({**valid_payload(), "external_purchase": value})

    def test_invalid_dates_are_rejected(self) -> None:
        for field in ("planned_start_date", "planned_end_date"):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    ProjectCreateSchema.model_validate({**valid_payload(), field: "2026-02-30"})

    def test_end_before_start_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValidationError, "计划结束日期不能早于计划开始日期"):
            ProjectCreateSchema.model_validate({**valid_payload(), "planned_end_date": "2026-10-31"})

    def test_same_day_project_is_accepted(self) -> None:
        project = ProjectCreateSchema.model_validate({**valid_payload(), "planned_end_date": "2026-11-01"})
        self.assertEqual(project.planned_start_date, project.planned_end_date)

    def test_extra_and_server_owned_fields_are_rejected(self) -> None:
        for field in ("created_id", "creator_user_id", "creator_dept_id", "status", "approver_ids", "unknown_field"):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError) as error:
                    ProjectCreateSchema.model_validate({**valid_payload(), field: 1})
                self.assertEqual(error.exception.errors()[0]["type"], "extra_forbidden")

    def test_json_round_trip(self) -> None:
        project = ProjectCreateSchema.model_validate_json(json.dumps(valid_payload()))
        self.assertEqual(project.model_dump(mode="json"), valid_payload())

    def test_json_schema_lists_ten_required_fields(self) -> None:
        schema = ProjectCreateSchema.model_json_schema()
        self.assertEqual(set(schema["required"]), set(valid_payload()))
        self.assertEqual(len(schema["required"]), 10)
        self.assertIs(schema["additionalProperties"], False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
