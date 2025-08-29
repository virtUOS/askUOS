# This code was adapted from https://github.com/MarvinIRW/Assessing-Answer-Accuracy-Hallucination-and-Document-Relevance-in-virtUOS-Chatbot/tree/main/code/eval

import os
import pandas as pd
from rouge_score import rouge_scorer


def compute_sentence_rouge(
    df: pd.DataFrame,
    reference_col: str,
    hypothesis_col: str,
    question_id_col: str,
    output_csv_path: str,
    mean_csv_path=None,
    dataset_lang=None,
) -> pd.DataFrame:
    """
    Compute sentence-level ROUGE for each row in `df` using the `evaluate` library.
    """

    references = df[reference_col].astype(str).tolist()
    hypotheses = df[hypothesis_col].astype(str).tolist()

    scorer = rouge_scorer.RougeScorer(["rouge1", "rouge2", "rougeL"], use_stemmer=True)

    # Compute ROUGE scores for each hypothesis/reference pair
    results = []
    for idx, (hyp, ref) in enumerate(zip(hypotheses, references)):
        score = scorer.score(ref, hyp)
        results.append(
            {
                question_id_col: df[question_id_col].iloc[idx],
                "ROUGE-1_p": score["rouge1"].precision,
                "ROUGE-1_r": score["rouge1"].recall,
                "ROUGE-1_f": score["rouge1"].fmeasure,
                "ROUGE-2_p": score["rouge2"].precision,
                "ROUGE-2_r": score["rouge2"].recall,
                "ROUGE-2_f": score["rouge2"].fmeasure,
                "ROUGE-L_p": score["rougeL"].precision,
                "ROUGE-L_r": score["rougeL"].recall,
                "ROUGE-L_f": score["rougeL"].fmeasure,
            }
        )

    # Build a new DataFrame
    result_df = pd.DataFrame()
    result_df[question_id_col] = df[question_id_col].values
    result_df = pd.concat(
        [result_df, pd.DataFrame(results).drop(columns=[question_id_col])], axis=1
    )

    # Compute macro averages for F1
    r1_f_mean = result_df["ROUGE-1_f"].mean()
    r1_r_mean = result_df["ROUGE-1_r"].mean()
    r1_p_mean = result_df["ROUGE-1_p"].mean()

    r2_f_mean = result_df["ROUGE-2_f"].mean()
    r2_r_mean = result_df["ROUGE-2_r"].mean()
    r2_p_mean = result_df["ROUGE-2_p"].mean()

    rl_f_mean = result_df["ROUGE-L_f"].mean()
    rl_r_mean = result_df["ROUGE-L_r"].mean()
    rl_p_mean = result_df["ROUGE-L_p"].mean()

    print(f"System-level average (macro) ROUGE scores for {output_csv_path}:")

    if (
        mean_csv_path is not None
        and os.path.exists(mean_csv_path)
        and dataset_lang is not None
    ):
        mean_eval = pd.read_csv(mean_csv_path)

        def add_metric(metric, value):
            if metric not in mean_eval["metric"].values:
                mean_eval.loc[len(mean_eval)] = {"metric": metric, "value": value}

        add_metric(f"  ROUGE-1_f: {r1_f_mean:.3f}")
        add_metric(f"  ROUGE-2_f: {r2_f_mean:.3f}")
        add_metric(f"  ROUGE-L_f: {rl_f_mean:.3f}")

        add_metric(f"  ROUGE-1_r: {r1_r_mean:.3f}")
        add_metric(f"  ROUGE-2_r: {r2_r_mean:.3f}")
        add_metric(f"  ROUGE-L_r: {rl_r_mean:.3f}")

        add_metric(f"  ROUGE-1_p: {r1_p_mean:.3f}")
        add_metric(f"  ROUGE-2_p: {r2_p_mean:.3f}")
        add_metric(f"  ROUGE-L_p: {rl_p_mean:.3f}\n")

        mean_eval.to_csv(mean_csv_path, index=False)

    result_df.to_csv(output_csv_path, index=False)
    print("Saved ROUGE metrics to:", output_csv_path)
    return result_df


def run_rouge_eval(config):
    csv_path_de = config.get("csv_path_de")
    mean_csv_path = config.get("csv_path_mean_rouge", None)
    output_csv_de = config.get("output_csv_rouge", None)
    if not csv_path_de or not output_csv_de:
        raise ValueError("csv_path_de and output_csv_rouge must be set in config.")

    df_de = pd.read_csv(csv_path_de)
    rouge_df_de = compute_sentence_rouge(
        df=df_de,
        reference_col="human_answer",
        hypothesis_col="chatbot_answer",
        question_id_col="question_id_q",
        output_csv_path=output_csv_de,
        mean_csv_path=mean_csv_path,
        dataset_lang="de",
    )
    return rouge_df_de
