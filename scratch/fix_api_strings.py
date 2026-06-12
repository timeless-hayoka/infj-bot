with open("/home/crexs/infj_bot/interfaces/api.py", "r") as f:
    content = f.read()

# Replace block 1
content = content.replace(
    '            (f"data: {json.dumps({\'error\': \'invalid JSON body\'})}\n\n" for _ in [1]),',
    '            (f"data: {json.dumps({\'error\': \'invalid JSON body\'})}\\n\\n" for _ in [1]),'
)
# Wait, let\'s look at how the actual split content is formatted in the file.
# In the file:
# 957:         return StreamingResponse(
# 958:             (f"data: {json.dumps({'error': 'invalid JSON body'})}
# 959: 
# 960: " for _ in [1]),
#
# So the search string has: '(f"data: {json.dumps({\'error\': \'invalid JSON body\'})}\n\n" for _ in [1]),' but with literal newline characters.
# Let\'s do a replace on the literal parts.

# Let\'s use a robust replace list of tuples:
replaces = [
    (
        '            (f"data: {json.dumps({\'error\': \'invalid JSON body\'})}\n\n" for _ in [1]),',
        '            (f"data: {json.dumps({\'error\': \'invalid JSON body\'})}\\n\\n" for _ in [1]),'
    ),
    (
        '            (f"data: {json.dumps({\'error\': \'message is required\'})}\n\n" for _ in [1]),',
        '            (f"data: {json.dumps({\'error\': \'message is required\'})}\\n\\n" for _ in [1]),'
    ),
    (
        '            (f"data: {json.dumps({\'chunk\': refusal})}\n\n" for _ in [1]),',
        '            (f"data: {json.dumps({\'chunk\': refusal})}\\n\\n" for _ in [1]),'
    ),
    (
        '            yield f"data: {json.dumps({\'error\': \'client disconnected\', \'code\': 499})}\n\n"',
        '            yield f"data: {json.dumps({\'error\': \'client disconnected\', \'code\': 499})}\\n\\n"'
    ),
    (
        '            yield "data: [DONE]\n\n"',
        '            yield "data: [DONE]\\n\\n"'
    ),
    (
        '            yield f"data: {json.dumps({\'error\': \'queue or request deadline exceeded\', \'code\': 429})}\n\n"',
        '            yield f"data: {json.dumps({\'error\': \'queue or request deadline exceeded\', \'code\': 429})}\\n\\n"'
    ),
    (
        '            yield f"data: {json.dumps({\'error\': f\'{type(exc).__name__}: {exc}\'})}\n\n"',
        '            yield f"data: {json.dumps({\'error\': f\'{type(exc).__name__}: {exc}\'})}\\n\\n"'
    )
]

# Wait, let\'s look at the actual source in content.
# Since python source contains literally:
#             (f"data: {json.dumps({'error': 'invalid JSON body'})}\n\n" for _ in [1]),
# where \n\n is actually two newlines in the text, let\'s verify.
# Let\'s do a simple regex or substring-based split cleanup.
import re

# We can replace:
# (f"data: {json.dumps({'error': 'invalid JSON body'})}\n\n" for _ in [1]),
# which is represented as:
# (f"data: {json.dumps({'error': 'invalid JSON body'})}\n\n\n\" for _ in [1]),
content = re.sub(
    r'\(f"data: \{json\.dumps\(\{\'error\': \'invalid JSON body\'\}\)\}\n\s*\n\s*"\s*for\s*_\s*in\s*\[1\]\)',
    r'(f"data: {json.dumps({\'error\': \'invalid JSON body\'})}\\n\\n" for _ in [1])',
    content
)

content = re.sub(
    r'\(f"data: \{json\.dumps\(\{\'error\': \'message is required\'\}\)\}\n\s*\n\s*"\s*for\s*_\s*in\s*\[1\]\)',
    r'(f"data: {json.dumps({\'error\': \'message is required\'})}\\n\\n" for _ in [1])',
    content
)

content = re.sub(
    r'\(f"data: \{json\.dumps\(\{\'chunk\': refusal\}\)\}\n\s*\n\s*"\s*for\s*_\s*in\s*\[1\]\)',
    r'(f"data: {json.dumps({\'chunk\': refusal})}\\n\\n" for _ in [1])',
    content
)

# For yields:
content = re.sub(
    r'yield f"data: \{json\.dumps\(\{\'error\': \'client disconnected\', \'code\': 499\}\)\}\n\s*\n\s*"',
    r'yield f"data: {json.dumps({\'error\': \'client disconnected\', \'code\': 499})}\\n\\n"',
    content
)

content = re.sub(
    r'yield f"data: \{json\.dumps\(\{\'error\': \'queue or request deadline exceeded\', \'code\': 429\}\)\}\n\s*\n\s*"',
    r'yield f"data: {json.dumps({\'error\': \'queue or request deadline exceeded\', \'code\': 429})}\\n\\n"',
    content
)

content = re.sub(
    r'yield f"data: \{json\.dumps\(\{\'error\': f\'\{type\(exc\)\.__name__\}: \{exc\}\'\}\)\}\n\s*\n\s*"',
    r'yield f"data: {json.dumps({\'error\': f\'{type(exc).__name__}: {exc}\'})}\\n\\n"',
    content
)

content = re.sub(
    r'yield "data: \[DONE\]\n\s*\n\s*"',
    r'yield "data: [DONE]\\n\\n"',
    content
)

with open("/home/crexs/infj_bot/interfaces/api.py", "w") as f:
    f.write(content)

print("SUCCESS: cleaned up f-strings in api.py.")
