from runner.agent import main

try:
    main()
except KeyboardInterrupt:
    print("Runner stopped.")
