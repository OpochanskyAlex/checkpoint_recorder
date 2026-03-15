import anthropic
import json
import os

#
config_file = "docs/config.json"
with open(config_file, "r") as f:
    config = json.load(f)

system_prompt_path = ""
agent_system_prompt_name = "01_Business_Thinker.md"
# agent_system_prompt_name = "02 Business Review Critic.md"
# agent_system_prompt_name = "03 Context Architect.md"
# agent_system_prompt_name = "04 System Critic.md"
# agent_system_prompt_name = "05 Architecture designer.md"
# agent_system_prompt_name = "06 Architecture Review Critic.md"
# agent_system_prompt_name = "07 Devil’s Advocate Report.md"
# agent_system_prompt_name = "08 IMPLEMENTATION SPECIFICATION ARCHITECT.md"

input_file = "docs/requirements/initial_task_setup.md"

with open(system_prompt_path + agent_system_prompt_name, "r", encoding="utf-8") as f:
    agent_system_prompt = f.read()

with open(input_file, "r", encoding="utf-8") as f:
    input = f.read()


client = anthropic.Anthropic(api_key=config.get("anthropic_api_key"))
def run_writer(input: str) -> str:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=agent_system_prompt,
        messages=[
            {"role": "user", "content": f"{input}"}
        ]
    )
    return response.content[0].text

run_writer(input)