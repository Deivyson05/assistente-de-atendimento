from fastapi import HTTPException, status

from api.chat.service import ChatService


class ChatController:
    def __init__(self, service: ChatService):
        self.service = service

    def chat(self, message: str, session_id: str) -> str:
        if not message.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mensagem vazia!")
        return self.service.send_message(message, session_id)
