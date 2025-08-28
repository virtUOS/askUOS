# 1. Run the llm as judge first
# 2. Save the results to be use by the the other metrics
# 3. Run the other metrics and save the results

"""
pip install ipykernel
python3 -m ipykernel install --user
"""

import json
import os

import nbformat
from nbconvert.preprocessors import ExecutePreprocessor

from eval.LLM_as_Judge import SemanticEvaluator


def execute_notebook(notebook_path, output_path):
    """Execute a Jupyter notebook and save the output."""
    with open(notebook_path) as f:
        nb = nbformat.read(f, as_version=4)

    ep = ExecutePreprocessor(timeout=600, kernel_name="python3")

    ep.preprocess(nb, {"metadata": {"path": os.path.dirname(notebook_path)}})

    with open(output_path, "w", encoding="utf-8") as f:
        nbformat.write(nb, f)


def run_evaluation_pipeline(
    save_results_path, test_data_path, save_results_notebook_path
):
    """Run the full evaluation pipeline including semantic evaluation."""
    cwd = os.getcwd()
    # Step 1: Run semantic evaluation
    semantic_evaluator = SemanticEvaluator(model_name="gpt-4o-mini")
    # Load test data
    test_data = semantic_evaluator.load_test_data(test_data_path)
    # Evaluate

    # semantic_evaluator.evaluate_dataset(test_data, save_results_path)

    notebook_config_path = os.path.join(cwd, "eval/notebook_config.json")
    with open(notebook_config_path, "w") as f:
        json.dump(
            {
                "csv_path_de": save_results_path,
                "csv_path_mean": os.path.join(cwd, "eval/results"),
                "output_csv_de": os.path.join(cwd, "eval/results"),
            },
            f,
        )

    # Step 2: Run bleu evaluation, with the results from the semantic evaluation
    notebook_path = os.path.join(cwd, "eval/bleu_eval.ipynb")
    output_notebook_path = os.path.join(
        save_results_notebook_path, "bleu_eval_executed.ipynb"
    )

    execute_notebook(notebook_path, output_notebook_path)

    # Step 3: Run rouge evaluation
    notebook_path = os.path.join(cwd, "eval/rouge_eval.ipynb")
    output_notebook_path = os.path.join(
        save_results_notebook_path, "rouge_eval_executed.ipynb"
    )
    execute_notebook(notebook_path, output_notebook_path)


def main():
    cwd = os.getcwd()  # if running in docker this will be /app
    # path to a csv containing the human labeled data. The csv should have the columns: question, expected_answer, source
    test_data_path = os.path.join(cwd, "eval/data/test_samples_german_faq.csv")
    save_results_path = os.path.join(cwd, "eval/results")
    # make sure the directory exists
    os.makedirs(save_results_path, exist_ok=True)

    save_results_notebook_path = os.path.join(cwd, "eval/results/notebooks")
    os.makedirs(save_results_notebook_path, exist_ok=True)
    # TODO: Make sure the data is in german. This file contains the human labeled data, chatbot answers and the llm as judge results
    save_results_path = os.path.join(save_results_path, "llm_judge_results_de.csv")

    run_evaluation_pipeline(
        save_results_path, test_data_path, save_results_notebook_path
    )


main()
