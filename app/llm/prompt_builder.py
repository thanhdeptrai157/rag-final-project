def build_rag_prompt(query: str, context: str) -> str:
    print("Building RAG prompt with context:", context)
    prompt = f"""
    Bạn là trợ lý trả lời câu hỏi dựa trên thông tin được cung cấp. Hãy sử dụng thông tin trong phần "Context" để trả lời câu hỏi một cách chính xác và đầy đủ nhất.
    [CONTEXT]
    {context}
    [/CONTEXT]
    [QUESTION]
    {query}
    [/QUESTION]
    Yêu cầu: 
    - Chỉ trả lời dựa trên context đã cho, không sử dụng kiến thức bên ngoài.
    - Nếu context không chứa đủ thông tin để trả lời, hãy trả lời "Không đủ thông tin".
    - Trả lời ngắn gọn, súc tích, không được bịa đặt thông tin.
    - Trả lời bằng tiếng Việt.
    """
    return prompt.strip()
