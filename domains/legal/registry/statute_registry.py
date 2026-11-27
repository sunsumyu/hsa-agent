import os
import yaml
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class GoverningLaw(BaseModel):
    code: str
    name: str
    article: str
    title: str

class EssentialElement(BaseModel):
    element_id: str
    name: str
    burden_of_proof: str
    is_mandatory_for_natural_person: bool = False
    ceiling_rule: Optional[str] = None
    accepted_evidence_types: List[str] = Field(default_factory=list)

class CauseOfActionSchema(BaseModel):
    cause_of_action: str
    governing_laws: List[GoverningLaw] = Field(default_factory=list)
    essential_elements: List[EssentialElement] = Field(default_factory=list)

    def get_element(self, element_id: str) -> Optional[EssentialElement]:
        for el in self.essential_elements:
            if el.element_id == element_id:
                return el
        return None

class StatuteRegistry:
    def __init__(self, directory: Optional[str] = None):
        if not directory:
            directory = os.path.join(os.path.dirname(__file__), "statutes")
        self.directory = directory
        self._cache: Dict[str, CauseOfActionSchema] = {}
        self._load_all()

    def _load_all(self):
        if not os.path.exists(self.directory):
            return
        for file in os.listdir(self.directory):
            if file.endswith(".yaml") or file.endswith(".yml"):
                path = os.path.join(self.directory, file)
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data and "cause_of_action" in data:
                        schema = CauseOfActionSchema(**data)
                        self._cache[schema.cause_of_action] = schema

    def get_cause_of_action(self, cause_name: str) -> Optional[CauseOfActionSchema]:
        return self._cache.get(cause_name)

statute_registry = StatuteRegistry()
