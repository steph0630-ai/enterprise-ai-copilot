from typing import Literal

from pydantic import BaseModel, Field, model_validator


Visibility = Literal["private", "department", "public"]


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    visibility: Visibility = "private"
    department: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def validate_department(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("知识库名称不能为空")
        self.department = self.department.strip() if self.department else None
        if self.visibility == "department" and not self.department:
            raise ValueError("部门知识库必须指定部门")
        if self.visibility != "department":
            self.department = None
        return self


class KnowledgeBaseUpdate(KnowledgeBaseCreate):
    pass


class KnowledgeBaseMemberCreate(BaseModel):
    user_id: int = Field(gt=0)
