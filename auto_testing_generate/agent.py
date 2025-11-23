import logging

from dotenv import load_dotenv
from langchain.agents import create_agent

load_dotenv()


agent = create_agent(model="openai:deepseek-chat", tools= [])
messages = {"messages": [{"role": "user", "content": "hi"}]}
invoke = agent.invoke(messages)
logging.info(invoke)
