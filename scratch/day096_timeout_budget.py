COLD_LOAD_SECONDS = 105.46
EVAL_TOKENS_PER_SECOND = 4.18
MAX_PREDICT_TOKENS = 300
SAFETY_FACTOR = 1.30   

decode_seconds = MAX_PREDICT_TOKENS / EVAL_TOKENS_PER_SECOND
estimated_seconds = COLD_LOAD_SECONDS + decode_seconds
budget_seconds = estimated_seconds * SAFETY_FACTOR

print("cold_load_seconds:", COLD_LOAD_SECONDS)
print("decode_seconds:", round(decode_seconds, 2))
print("estimated_seconds:", round(estimated_seconds, 2))
print("budget_with_safety:", round(budget_seconds, 2))
print("selected_read_timeout_seconds:", 240)
print("selected_nginx_timeout_seconds:", 300)