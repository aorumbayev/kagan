# Iteration {iteration} of {max_iterations}

## Task: {title}

{description}

{hat_instructions}

## Your Progress So Far

{scratchpad}

## Instructions

1. Review your previous progress above (if any)
2. Continue working on the task
3. Make incremental progress - don't try to do everything at once
4. Run tests/builds to verify your changes work
5. Commit your changes with descriptive messages

## CRITICAL: Response Signal Required

You MUST end your response with exactly ONE of these XML signals:

- `<complete/>` - Task is FULLY DONE and verified working
- `<continue/>` - Made progress, need another iteration to finish
- `<blocked reason="why"/>` - Cannot proceed without human help

**If you completed the task successfully, you MUST output `<complete/>` as the last thing in your response.**

Example ending:
```
I've implemented the feature and verified it works.
<complete/>
```
