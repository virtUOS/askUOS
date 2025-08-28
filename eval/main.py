import json
import os

from eval.BERTscore_eval import run_bertscore_eval
from eval.bleu_eval import run_bleu_eval
from eval.LLM_as_Judge import SemanticEvaluator

from eval.rouge_eval import run_rouge_eval


def run_semantic_evaluation(save_results_path, test_data_path):
    evaluator = SemanticEvaluator(model_name="gpt-4o-mini")
    test_data = evaluator.load_test_data(test_data_path)
    evaluator.evaluate_dataset(test_data, save_results_path)


def load_config(config_path):
    with open(config_path, "r") as f:
        config = json.load(f)
    return config


def main():
    cwd = os.getcwd()
    # Paths
    test_data_path = os.path.join(cwd, "eval/data/test_samples_german_faq.csv")
    results_dir = os.path.join(cwd, "eval/results")
    os.makedirs(results_dir, exist_ok=True)
    llm_judge_results_path = os.path.join(results_dir, "llm_judge_results_de.csv")

    # 1. Run LLM as Judge and save results
    print("Running LLM as Judge (semantic evaluation)...")
    # run_semantic_evaluation(llm_judge_results_path, test_data_path)

    # 2. Prepare config for metrics
    config = {
        "csv_path_de": llm_judge_results_path,
        "csv_path_mean_bleu": os.path.join(results_dir, "mean_eval_bleu_de.csv"),
        "csv_path_mean_rouge": os.path.join(results_dir, "mean_eval_rouge_de.csv"),
        "csv_path_mean_bert": os.path.join(results_dir, "mean_eval_bert_score_de.csv"),
        "output_csv_bleu": os.path.join(results_dir, "bleu_evaluation_de.csv"),
        "output_csv_rouge": os.path.join(results_dir, "rouge_evaluation_de.csv"),
        "output_csv_bert": os.path.join(results_dir, "bert_score_evaluation_de.csv"),
    }

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


if __name__ == "__main__":
    main()
