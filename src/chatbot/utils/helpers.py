def compute_search_num_tokens(search_result_text: str) -> int:

    # search_result_text_tokens = self._llm.get_num_tokens(search_result_text)
    # return search_result_text_tokens
    # 1 token ≈ 4 characters (Only an approximation)
    return len(search_result_text) // 4
