from langchain_core.prompts import SystemMessagePromptTemplate
from langchain.prompts.prompt import PromptTemplate
from langchain.prompts.chat import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
)

"""
this is what the prompt looks like once rendered:

[ChatPromptValue(messages=[SystemMessage(content='You work for a german university as an advisor who supports prospect students with their application process.\n                           Provide answers in German if the student asks in German, and in English if the student asks in English.\n                             The AI is talkative and provides lots of specific details from its context.\n                          If the AI does not know the answer to a question, it truthfully says it does not know.\n                Answer any user questions based solely on the context below:\n\n<context>\nBitte lesen Sie alle folgenden Hinweise zum Bewerber-Login aufmerksam durch.\n2.3.1 E-Mail-Verifikation\n\nNach der erstmaligen Registrierung in unserem Portal bekommen Sie eine Registrierungsmail mit Ihrer Benutzungsrkennung und einem Freischaltcode bzw. Verifizierungslink. Bitte vergessen Sie nicht Ihre Registrierung zu verifizieren.\n2.3.2 Über welche Funktion melde ich mich an?\n\n1.1 Welche Browser werden derzeit unterstützt?\n\nWenn Sie das Bewerbungsportal mit dem Browser „Microsoft Edge“ benutzen, funktionieren einige Funktionen derzeit nicht. Bitte benutzen Sie einen anderen Browser, wie z.B. Mozilla Firefox, Internet Explorer oder Chrome.\nZurück nach oben\n2 Probleme bei der Registrierung / mit dem Login\n\n2.1 Bei der erstmaligen Registrierung, nach dem Klick auf „Registrieren“, komme ich nicht weiter. Die Seite wird ohne Fehler nochmal geladen. Wieso?\n</context>'), HumanMessage(content='Name three study programs at the University')])]

You are an AI assistant for the University of Osnabrueck Germany. You support prospect students with their application process. The University website is https://www.uni-osnabrueck.de/startseite.
You are given the following extracted parts of a long document and a question. Provide a conversational answer with a hyperlink to the documentation.
You should only use hyperlinks that are explicitly listed as a source in the context. Do NOT make up a hyperlink that is not listed.

If you don't know the answer, just say "Hmm, I'm not sure." Don't try to make up an answer.
If the question is not about LangChain, politely inform them that you are tuned to only answer questions about LangChain.
Question: {question}
=========
{context}
=========


"""

# \n\n<chat history>\n{chat_history}\n</chat history>

template_text ="""
Assume the role of a German university advisor who works for the University of Osnabrück in Germany. You support people who are interested in studying at the University of Osnabrück.
# Your Tasks:
- Answer questions about applying to the University of Osnabrück in Germany.
- Answer questions about studying at the University of Osnabrück in Germany.
- If the user asks a question in German, generate the answer in German. If the user asks a question in English, generate the answer in English.
- If you do not know the answer to a question, just say "I don't know."
- If the user asks a question that is not about University studies in Germany, just say "I can only answer questions related to studying at the University of Osnabrück."
- Be talkative and provide lots of specific details from the context.
- Provide answers based  on the context and chat history provided below.
- If the context provided doesn't contain any relevant information to the question, don't make something up and just say "I don't know."
- Provide relevant links when these are provided by the context.
\n 
Context: 

{context}
\n 
Chat History:

{chat_history}
                                                            
"""


template_messages = [SystemMessagePromptTemplate(prompt=PromptTemplate(input_variables=['context', 'chat_history'],
                                                                       template=template_text)),
                     MessagesPlaceholder(variable_name='chat_history'),
                     HumanMessagePromptTemplate(prompt=PromptTemplate(input_variables=['question'], template='{question}'))]



prompt_template = ChatPromptTemplate.from_messages(template_messages)
