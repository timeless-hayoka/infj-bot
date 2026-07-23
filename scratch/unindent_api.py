with open("/home/crexs/drift/interfaces/api.py", "r") as f:
    lines = f.readlines()

start_line = 781  # 0-indexed line 782
end_line = 1132  # 0-indexed line 1133 (exclusive)

print("Starting verification:")
print("Start line is:", repr(lines[start_line]))
print("End line is:", repr(lines[end_line]))

if (
    "async def read_json" in lines[start_line]
    and '@app.post("/api/command")' in lines[end_line]
):
    # Unindent lines by 4 spaces
    for i in range(start_line, end_line):
        if lines[i].startswith("    "):
            lines[i] = lines[i][4:]
    with open("/home/crexs/drift/interfaces/api.py", "w") as f:
        f.writelines(lines)
    print("SUCCESS: Unindented lines 782 to 1132 successfully.")
else:
    print("ERROR: Target line verification failed. Indices might be shifted.")
