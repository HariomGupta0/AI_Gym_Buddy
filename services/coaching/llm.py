from services.config.workout_config import PROMPT


class LLMCoach:
    def __init__(self,groq_client):
        self.client = groq_client
        self.history = []
        self.system_prompt = PROMPT

    def give_feedback(self, event, issue):
        prompt = f"Event: {event}"

        if issue:
            prompt += f"Form Issue: {issue}"

        messages = [
            {"role": "system", "content": self.system_prompt},
            *self.history[-10:],
            {"role": "user", "content": prompt}
        ]

        response = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.4
        )

        text = response.choices[0].message.content.strip()

        self.history.append({"role": "assistant", "content": text})

        return text
        