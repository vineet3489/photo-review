from pydantic import BaseModel, Field
from typing import List, Literal, Dict

class Score(BaseModel):
    vibeCheck: float = Field(ge=0, le=10)
    firstImpression: float = Field(ge=0, le=10)
    lifestyle: float = Field(ge=0, le=10)
    styleAndPresence: float = Field(ge=0, le=10)

class PhotoFeedback(BaseModel):
    photo_title: str
    green_flags: List[str]
    red_flags: List[str]
    verdict: Literal["keep_it", "change_it"]
    score: Score
    action_points: List[str]

class AnalyzedItem(BaseModel):
    filename: str
    image_url: str
    feedback: PhotoFeedback

class AnalyzeResponse(BaseModel):
    items: List[AnalyzedItem]
    overall: Dict

class ImproveItem(BaseModel):
    filename: str
    original_url: str
    improved_url: str
    prompt_used: str

class ProcessResponse(BaseModel):
    analysis: AnalyzeResponse
    improvements: List[ImproveItem]

