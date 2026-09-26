from langchain.chat_models import init_chat_model

import dotenv
dotenv.load_dotenv()

SONET4_6 = init_chat_model("claude-sonnet-4-6")