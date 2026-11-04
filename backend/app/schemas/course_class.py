"""CourseClass read models and Admin create/update/status schemas (Spec Sections 04, 08, 09, 14, 15)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.core.errors import FieldErrorCode
from app.schemas.common import PaginationSchema, ResponseModel, StrictRequestModel

DayOfWeek = Literal["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
ClassStatus = Literal["OPEN", "CLOSED"]
RegistrationViewStatus = Literal["REGISTERED", "NOT_REGISTERED"]
CourseClassPaymentViewStatus = Literal["UNPAID", "PAID"]


class ScheduleItemSchema(StrictRequestModel):
    day_of_week: DayOfWeek = Field(..., examples=["MON"])
    start_period: int = Field(..., ge=1, le=12, examples=[1])
    end_period: int = Field(..., ge=1, le=12, examples=[3])
    room: str = Field(..., examples=["A101"])

    @field_validator("room")
    @classmethod
    def check_room(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise PydanticCustomError(
                "room_empty",
                "Phòng học không được để trống.",
                {"field_code": FieldErrorCode.INVALID_FORMAT},
            )
        if len(cleaned) > 100:
            raise PydanticCustomError(
                "room_too_long",
                "Tên phòng học tối đa 100 ký tự.",
                {"field_code": FieldErrorCode.OUT_OF_RANGE},
            )
        return cleaned

    @model_validator(mode="after")
    def check_period_order(self) -> ScheduleItemSchema:
        if self.start_period > self.end_period:
            raise PydanticCustomError(
                "period_order",
                "Tiết bắt đầu không được lớn hơn tiết kết thúc.",
                {"field_code": FieldErrorCode.INVALID_FORMAT},
            )
        return self


class PrerequisiteItemSchema(ResponseModel):
    course_code: str = Field(..., examples=["CS101"])
    course_name: str = Field(..., examples=["Nhập môn lập trình"])
    satisfied: bool | None = Field(default=None, examples=[False])


class CourseClassSchema(ResponseModel):
    course_class_id: str = Field(..., examples=["LHP001"])
    class_code: str = Field(..., examples=["CNNT-01"])
    course_code: str = Field(..., examples=["CNNT"])
    course_name: str = Field(..., examples=["Công nghệ nền tảng"])
    credits: int = Field(..., ge=1, examples=[3])
    capacity: int = Field(..., ge=1, examples=[50])
    remaining_seats: int = Field(..., ge=0, examples=[50])
    registered_count: int = Field(..., ge=0, examples=[0])
    status: ClassStatus = Field(..., examples=["OPEN"])
    schedule: list[ScheduleItemSchema] = Field(default_factory=list)
    prerequisites: list[PrerequisiteItemSchema] = Field(default_factory=list)
    tuition_amount: int = Field(..., ge=0, examples=[1500000])
    registration_status: RegistrationViewStatus = Field(..., examples=["NOT_REGISTERED"])
    registration_id: str | None = Field(default=None, examples=[None])
    payment_status: CourseClassPaymentViewStatus | None = Field(default=None, examples=[None])


class CourseClassListData(ResponseModel):
    items: list[CourseClassSchema]
    pagination: PaginationSchema


class CourseClassDetailData(ResponseModel):
    course_class: CourseClassSchema


class AdminCourseClassUpsertRequest(StrictRequestModel):
    class_code: str = Field(..., examples=["CNNT-01"])
    course_code: str = Field(..., examples=["CNNT"])
    course_name: str = Field(..., examples=["Công nghệ nền tảng"])
    credits: int = Field(..., ge=1, le=30, examples=[3])
    capacity: int = Field(..., ge=1, le=10000, examples=[50])
    status: ClassStatus = Field(..., examples=["OPEN"])
    schedule: list[ScheduleItemSchema] = Field(..., examples=[[]])
    prerequisite_course_codes: list[str] = Field(..., examples=[[]])

    @field_validator("class_code", "course_code")
    @classmethod
    def check_code_str(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise PydanticCustomError(
                "code_empty",
                "Mã không được để trống.",
                {"field_code": FieldErrorCode.INVALID_FORMAT},
            )
        if len(cleaned) > 32:
            raise PydanticCustomError(
                "code_len",
                "Mã tối đa 32 ký tự.",
                {"field_code": FieldErrorCode.OUT_OF_RANGE},
            )
        return cleaned

    @field_validator("course_name")
    @classmethod
    def check_course_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise PydanticCustomError(
                "name_empty",
                "Tên học phần không được để trống.",
                {"field_code": FieldErrorCode.INVALID_FORMAT},
            )
        if len(cleaned) > 200:
            raise PydanticCustomError(
                "name_len",
                "Tên học phần tối đa 200 ký tự.",
                {"field_code": FieldErrorCode.OUT_OF_RANGE},
            )
        return cleaned

    @field_validator("prerequisite_course_codes")
    @classmethod
    def check_prereq_codes(cls, values: list[str]) -> list[str]:
        cleaned_list: list[str] = []
        seen: set[str] = set()
        for item in values:
            cleaned = item.strip()
            if not cleaned or len(cleaned) > 32:
                raise PydanticCustomError(
                    "prereq_code_format",
                    "Mã học phần tiên quyết phải dài 1–32 ký tự.",
                    {"field_code": FieldErrorCode.INVALID_FORMAT},
                )
            if cleaned in seen:
                raise PydanticCustomError(
                    "prereq_duplicate",
                    f"Mã học phần tiên quyết '{cleaned}' bị lặp.",
                    {"field_code": FieldErrorCode.INVALID_FORMAT},
                )
            seen.add(cleaned)
            cleaned_list.append(cleaned)
        return cleaned_list

    @model_validator(mode="after")
    def check_self_prereq_and_schedule_overlap(self) -> AdminCourseClassUpsertRequest:
        if self.course_code in self.prerequisite_course_codes:
            raise PydanticCustomError(
                "self_prerequisite",
                "Học phần không thể tự là tiên quyết của chính nó.",
                {"field_code": FieldErrorCode.INVALID_FORMAT},
            )
        # Prevent overlapping schedule slots inside the same class definition
        for i in range(len(self.schedule)):
            for j in range(i + 1, len(self.schedule)):
                s1 = self.schedule[i]
                s2 = self.schedule[j]
                if s1.day_of_week == s2.day_of_week and max(
                    s1.start_period, s2.start_period
                ) <= min(s1.end_period, s2.end_period):
                    raise PydanticCustomError(
                        "internal_schedule_overlap",
                        "Lịch học của cùng một lớp không được tự chồng lấn tiết học.",
                        {"field_code": FieldErrorCode.INVALID_FORMAT},
                    )
        return self


class AdminCourseClassStatusRequest(StrictRequestModel):
    status: ClassStatus = Field(..., examples=["CLOSED"])
