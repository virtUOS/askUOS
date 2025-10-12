import datetime
import json
import os
import subprocess

from eval_generation.BERTscore_eval import run_bertscore_eval
from eval_generation.bleu_eval import run_bleu_eval
from eval_generation.LLM_as_Judge import SemanticEvaluator
from eval_generation.rouge_eval import run_rouge_eval


def run_semantic_evaluation(save_results_path, test_data_path):
    evaluator = SemanticEvaluator(model_name="gpt-4o-mini")
    test_data = evaluator.load_test_data(test_data_path)
    evaluator.evaluate_dataset(test_data, save_results_path)


def load_config(config_path):
    with open(config_path, "r") as f:
        config = json.load(f)
    return config


def run_notebook_with_date(input_notebook_path, output_dir):
    """
    Executes a Jupyter notebook and saves the output with the current date in the filename.
    """
    date_str = datetime.datetime.now().strftime("%Y%m%d")
    base_name = os.path.splitext(os.path.basename(input_notebook_path))[0]
    output_notebook = f"{base_name}_{date_str}.ipynb"
    output_path = os.path.join(output_dir, output_notebook)
    # Run the notebook and save the output
    subprocess.run(
        [
            "jupyter",
            "nbconvert",
            "--to",
            "notebook",
            "--execute",
            "--output",
            output_path,
            input_notebook_path,
        ],
        check=True,
    )
    print(f"Executed notebook saved to: {output_path}")


def main():
    cwd = os.getcwd()
    # Paths
    test_data_path = os.path.join(
        cwd, "eval_generation/data/test_samples_german_faq.csv"
    )
    date_str = datetime.datetime.now().strftime("%Y%m%d")
    results_dir = os.path.join(cwd, f"eval_generation/results/results_{date_str}")
    os.makedirs(results_dir, exist_ok=True)
    llm_judge_results_path = os.path.join(results_dir, "llm_judge_results_de.csv")

    # 1. Run LLM as Judge and save results
    print("Running LLM as Judge (semantic evaluation)...")
    run_semantic_evaluation(llm_judge_results_path, test_data_path)

    # 2. Prepare config for metrics
    config = {
        "csv_path_de": llm_judge_results_path,  # contais llm judge results and bot generated answers.
        "csv_path_mean_bleu": os.path.join(results_dir, "mean_eval_bleu_de.csv"),
        "csv_path_mean_rouge": os.path.join(results_dir, "mean_eval_rouge_de.csv"),
        "csv_path_mean_bert": os.path.join(results_dir, "mean_eval_bert_score_de.csv"),
        "output_csv_bleu": os.path.join(results_dir, "bleu_evaluation_de.csv"),
        "output_csv_rouge": os.path.join(results_dir, "rouge_evaluation_de.csv"),
        "output_csv_bert": os.path.join(results_dir, "bert_score_evaluation_de.csv"),
    }

    # save paths to json file. The file will be used by notebooks
    config_path = os.path.join(cwd, "eval_generation/result_paths.json")
    with open(config_path, "w") as f:
        json.dump(config, f, indent=4)

    # 3. Run BLEU evaluation
    print("Running BLEU evaluation...")
    df_bleu = run_bleu_eval(config)

    # 4. Run ROUGE evaluation
    print("Running ROUGE evaluation...")
    df_rouge = run_rouge_eval(config)

    # 5. Run BERTScore evaluation
    print("Running BERTScore evaluation...")
    df_bert = run_bertscore_eval(config)

    print("All metrics computed and saved.")

    # 6. run notebooks for visualization
    notebook_path = os.path.join(
        cwd, "eval_generation/automatic_eval/lexical_semantic_eval.ipynb"
    )
    run_notebook_with_date(notebook_path, results_dir)

    print("Evaluation pipeline completed.")


if __name__ == "__main__":
    main()
