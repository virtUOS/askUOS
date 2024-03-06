from tkinter import *
from chain_chatbots.llama2_chat import GetAnswer


# GUI --> https://www.geeksforgeeks.org/gui-chat-application-using-tkinter-in-python/
root = Tk()
root.title("Chatbot")

BG_GRAY = "#ABB2B9"
BG_COLOR = "#17202A"
TEXT_COLOR = "#EAECEE"

FONT = "Helvetica 14"
FONT_BOLD = "Helvetica 13 bold"

# Send function
def send():
	send = "You -> " + e.get()
	txt.insert(END, "\n" + send)

	user_message = e.get().lower()

	# print(f"Retrieving documents for question: {user_message}")
	# docs = get_docs(user_message)
	# print(
	# 	f"Retrieved {len(docs)} documents for question: {user_message}. -------------------{docs}"
	# )
	# response = chain.invoke({"input_documents": docs, "question": user_message})
	response = GetAnswer.predict(user_message)

	txt.insert(END, "\n" + f"Bot -> {response}")


	e.delete(0, END)


lable1 = Label(root, bg=BG_COLOR, fg=TEXT_COLOR, text="Welcome", font=FONT_BOLD, pady=10, width=20, height=1).grid(
	row=0)

txt = Text(root, bg=BG_COLOR, fg=TEXT_COLOR, font=FONT, width=60)
txt.grid(row=1, column=0, columnspan=2)

scrollbar = Scrollbar(txt)
scrollbar.place(relheight=1, relx=0.974)

e = Entry(root, bg="#2C3E50", fg=TEXT_COLOR, font=FONT, width=55)
e.grid(row=2, column=0)

send = Button(root, text="Send", font=FONT_BOLD, bg=BG_GRAY,
			command=send).grid(row=2, column=1)

root.mainloop()
