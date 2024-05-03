from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import re
import anthropic
import markdown
from dotenv import load_dotenv  # Import load_dotenv from dotenv
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Gunicorn log settings
loglevel = 'info'
accesslog = 'flagged/access.log'
errorlog = 'flagged/error.log'

# Custom log format
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Setup logging
logger = logging.getLogger('gunicorn.error')
logger.setLevel(loglevel.upper())

app = Flask(__name__, static_folder='static')
logger.info('Flask app initialized')
CORS(app, resources={r"/*": {"origins": ["*.vercel.app"]}})

load_dotenv()  # Load environment variables from .env file

API_KEY = os.environ.get("ANTHROPIC_API_KEY")
if API_KEY is None:
    raise ValueError("Anthropic API key not found in environment variables.")

CLIENT = anthropic.Anthropic(api_key=API_KEY)

SYSTEM_ROLE = """
You are an expert in ethics conducting a comprehensive analysis of this situation. 
Follow established ethical frameworks and principles. 
Please keep your responses very concise and precise. 
Always use markdown format for clarity (e.g., headings, code blocks, bold, > quotes, - unordered lists). 
For each step, please provide a detailed analysis in the corresponding tags (<problem>, <principles>, <dimensions>, <actions>, <consequences>, or <answer>). 
For example, a well-structured response for the first step might look like this: 
<step_tag>
<problem>
My analysis of this step involves considering [insert relevant factors or principles].
This leads me to conclude that [insert conclusion].
</problem>
[Insert response]
</step_tag>
Please ONLY use `<answer>` tags once, ALWAYS around final response. 
If you are unable to respond, reply 'incomplete' with no explanation."
"""

STEPS = [
    ("Identify the ethical problem or dilemma in the following situation: {prompt}.", "<problem>"),
    ("Apply relevant ethical codes, principles, or frameworks to the identified problem", "<principles>"),
    ("Considering the principles, determine the nature and dimensions of the ethical dilemma, considering all stakeholders and potential consequences", "<dimensions>"),
    ("Given the dimensions, generate potential courses of action to address the ethical dilemma", "<actions>"),
    ("For each course of action, what are the potential consequences, and how do they align with the principles?", "<consequences>"),
    ("Based on the analysis, what is the most ethically justifiable course of action, and why does it align with the relevant principles and minimize harm to stakeholders?", "<answer>")
]

def build_grader_prompt(answer, rubric):
    user_content = f"""You will be provided an answer that an assistant gave to one step (prompt) in its chain-of-thought reasoning of this ethical dilemma, and a rubric that instructs you on what makes the answer correct or incorrect.
    
    Here is the answer that the assistant gave to the question.
    <answer>{answer}</answer>
    
    Here is the rubric on what makes the answer correct or incorrect.
    <rubric>{rubric}</rubric>
    
    An answer is correct if it mostly meets the rubric criteria, and otherwise it is incorrect.
    First, think through whether the answer is correct or incorrect based on the rubric inside <thinking></thinking> tags. Then assign an overall score out of 100 in <score> tags. Finally, output either 'correct' if the answer is correct or 'incorrect' if the answer is incorrect inside <correctness></correctness> tags."""

    messages = [{'role': 'user', 'content': user_content}]
    return messages

def get_completion(messages):
    completion = []
    for message in messages:
        completion.append(message.text)
    return ''.join(completion)

def grade_completion(output, rubric):
    try:
        # print("Building grader prompt...")
        messages = build_grader_prompt(output, rubric)
        # print("Messages built:", messages)
        completion = CLIENT.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=256,
            temperature=0.2,
            messages=messages
        ).content
        # print("API Response:", completion)

        if isinstance(completion, list):
            completion_text = ''.join([block.text for block in completion])
        else:
            completion_text = completion

        return {"response": completion_text}
    except Exception as e:
        print("Detailed error:", str(e))
        raise RuntimeError(f"Error during grading: {str(e)}") from e
    
def ethical_analysis(prompt: str, anthropic_client: anthropic.Anthropic) -> str:
    try:
        # Replace {prompt} with the actual prompt
        step_templates = [step.format(prompt=prompt) for step, tag in STEPS]
        combined_prompt = "\n".join([f"{step}\n{tag}" for step, tag in zip(step_templates, STEPS)])

        response = anthropic_client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=2048,
            temperature=0.2,
            system=SYSTEM_ROLE,
            messages=[
                {
                    "role": "user",
                    "content": combined_prompt
                }
            ]
        ).content

        # Print the raw response from Claude
        # print("Raw response from Claude:")
        # print(response)

        # Extract the analysis result from the response
        analysis_result = get_completion(response)

        return {"analysis": analysis_result}
    
    except Exception as e:
        logging.exception(f"An unexpected error occurred: {e}")
        logger.exception(f"An unexpected error occurred: {e}")
        return {"error": {"message": str(e), "type": "internal_server_error"}}

@app.route('/analysis', methods=['POST'])
def analyze_ethics():
    try:
        data = request.json
        situation = data.get('situation')
        if not situation:
            logging.error('Situation not provided')
            logger.error('Situation not provided')
            return jsonify({
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "message": "Situation not provided."
                }
            }), 400

        logging.info('Performing ethical analysis')
        logger.info('Performing ethical analysis')
        analysis_results = ethical_analysis(situation, CLIENT)
        logging.info('Ethical analysis completed')
        logger.info('Ethical analysis completed')
        return jsonify(analysis_results)
    except Exception as e:
        logging.exception(f"An unexpected error occurred: {e}")
        logger.exception(f"An unexpected error occurred: {e}")
        return jsonify({
            "type": "error",
            "error": {
                "type": "internal_server_error",
                "message": str(e)
            }
        }), 500
        
@app.route('/eval', methods=['POST'])
def evaluate_completion():
    try:
        data = request.json
        prompt = data.get('prompt')
        completion = data.get('completion')
        rubric = data.get('rubric')
        if not prompt or not completion or not rubric:
            logging.error('Prompt, completion, or rubric not provided')
            logger.error('Prompt, completion, or rubric not provided')
            return jsonify({"error": "Prompt, completion, or rubric not provided"}), 400

        logging.info('Evaluating completion')
        logger.info('Evaluating completion')
        result = grade_completion(completion, rubric)
        logging.info('Completion evaluation completed')
        logger.info('Completion evaluation completed')
        return jsonify(result)
    except Exception as e:
        logging.exception(f"An unexpected error occurred: {e}")
        logger.exception(f"An unexpected error occurred: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/steps', methods=['GET'])
def get_steps():
    steps_with_tags = [
        ("<prompt>" + step + "</prompt>", tag)
        for step, tag in STEPS
    ]
    return jsonify(steps_with_tags)

# Serve React App
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    logger.info(f'Serving path: {path}')
    logging.info(f'Serving path: {path}')
    if path != "" and os.path.exists(app.static_folder + '/' + path):
        return send_from_directory(app.static_folder, path)
    else:
        logging.warning(f'Serving index.html for path: {path}')
        logger.warning(f'Serving index.html for path: {path}')
        return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0')
