# Boot loop
    while True:
        try:
            user_input = input("\n[JUDE] (Type 'exit' to close): ")
            
            # --- The new transparent CLI commands ---
            if user_input.lower() == "manifesto":
                print("\n[MOUSE CONSTITUTION]")
                for rule in mouse.identity.constitution:
                    print(f"  - {rule}")
                continue
                
            if user_input.lower() == "cortex":
                print("\n[ACTIVE MEMORY CORTEX]")
                print(mouse.summarize_memory(limit=5))
                continue
            # ----------------------------------------
            
            if user_input.lower() in ['exit', 'quit']:
                print("\n[SYSTEM] Shutting down Symbiotic Framework. Memory saved.")
                break
                
            if user_input.strip() == "":
                continue
                
            run_cognitive_turn(mouse, ollama, user_input)
            
        except KeyboardInterrupt:
            print("\n\n[SYSTEM] Force termination detected. Memory saved. Goodbye.")
            break