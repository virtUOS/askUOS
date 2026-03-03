const response = await fetch("/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: "What are the deadlines?", thread_id: "abc-123" }),
});

const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = "";

while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n\n");
    buffer = lines.pop(); // keep incomplete chunk

    for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const event = JSON.parse(line.slice(6));

        switch (event.type) {
            case "chunk":
                // Append token to UI
                appendToChat(event.content);
                break;
            case "full":
                // Display complete response
                setChat(event.content);
                break;
            case "references":
                // Show links and docs below the answer
                showReferences(event.links, event.doc_references);
                break;
            case "error":
                showError(event.message);
                break;
            case "done":
                // Streaming complete
                break;
        }
    }
}