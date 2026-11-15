import logging

from fastapi import APIRouter, HTTPException, status

from app.agents.tutor_agent import TutorOutputError
from app.conversation.chat_service import ChatNotFoundError, TutorChatService
from app.conversation.schemas import (
    CreateTutorChatRequest,
    CreateTutorChatResponse,
    QuizAnswerResponse,
    SubmitQuizAnswerRequest,
    SendTutorMessageRequest,
    TutorChatListItem,
    TutorHistoryResponse,
    TutorMessageResponse,
    TutorQuizResponse,
)
from app.llm.zoho_quickml import ZohoRequestTooLargeError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tutor", tags=["Tutor"])
chat_service = TutorChatService()


@router.post("/chats", response_model=CreateTutorChatResponse, status_code=status.HTTP_201_CREATED)
def create_chat(request: CreateTutorChatRequest):
    return chat_service.create_chat(request.lesson_title, request.lesson_content)


@router.get("/chats", response_model=list[TutorChatListItem])
def list_chats():
    return chat_service.list_chats()


@router.get("/chats/{chat_id}/messages", response_model=TutorHistoryResponse)
def get_chat_history(chat_id: str):
    try:
        return chat_service.get_history(chat_id)
    except ChatNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/chats/{chat_id}/messages", response_model=TutorMessageResponse)
def send_message(chat_id: str, request: SendTutorMessageRequest):
    try:
        return chat_service.send_message(chat_id, request.message, request.mode)
    except ChatNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ZohoRequestTooLargeError as exc:
        logger.warning("Zoho rejected tutor prompt as too large: %s", exc)
        raise HTTPException(
            status_code=413,
            detail=(
                "The tutor context is still too large for the configured Zoho endpoint. "
                "Try a shorter question or create a new chat for this lesson."
            ),
        ) from exc
    except Exception as exc:
        logger.exception("Tutor model request failed")
        raise HTTPException(
            status_code=502,
            detail="Tutor model request failed. Check the API server logs.",
        ) from exc


@router.post("/chats/{chat_id}/quiz", response_model=TutorQuizResponse)
def create_quiz(chat_id: str):
    try:
        return chat_service.create_quiz(chat_id)
    except ChatNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TutorOutputError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ZohoRequestTooLargeError as exc:
        logger.warning("Zoho rejected tutor quiz prompt as too large: %s", exc)
        raise HTTPException(
            status_code=413,
            detail="The lesson context is too large for quiz generation. Try a shorter lesson.",
        ) from exc
    except Exception as exc:
        logger.exception("Tutor quiz generation failed")
        raise HTTPException(
            status_code=502,
            detail="Quiz generation failed. Check the API server logs.",
        ) from exc


@router.post("/chats/{chat_id}/quiz/answer", response_model=QuizAnswerResponse)
def submit_quiz_answer(chat_id: str, request: SubmitQuizAnswerRequest):
    try:
        return chat_service.submit_quiz_answer(chat_id, request.option_id)
    except ChatNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
