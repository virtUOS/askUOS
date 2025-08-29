# This code was adapted from https://github.com/MarvinIRW/Assessing-Answer-Accuracy-Hallucination-and-Document-Relevance-in-virtUOS-Chatbot/tree/main/code/eval

import os
import pandas as pd
from sacrebleu.metrics import BLEU


def compute_sentence_bleu(
    df: pd.DataFrame,
    reference_col: str,
    hypothesis_col: str,
    question_id_col: str,
    output_csv_path: str,
    mean_csv_path=None,
    dataset_lang=None,
    bleu_metric=None,
) -> pd.DataFrame:
    """
    Compute sentence-level BLEU for each row in the given DataFrame.
    """
    if bleu_metric is None:
        bleu_metric = BLEU(effective_order=True)

    references = df[reference_col].astype(str).tolist()
    hypotheses = df[hypothesis_col].astype(str).tolist()

    bleu_scores = []
    bleu_1gram_precision = []
    bleu_2gram_precision = []
    bleu_3gram_precision = []
    bleu_4gram_precision = []
    bleu_bp = []
    bleu_sys_len = []
    bleu_ref_len = []

    for hyp, ref in zip(hypotheses, references):
        result = bleu_metric.sentence_score(hyp, [ref])
        bleu_scores.append(result.score)
        bleu_1gram_precision.append(result.precisions[0])
        bleu_2gram_precision.append(result.precisions[1])
        bleu_3gram_precision.append(result.precisions[2])
        bleu_4gram_precision.append(result.precisions[3])
        bleu_bp.append(result.bp)
        bleu_sys_len.append(result.sys_len)
        bleu_ref_len.append(result.ref_len)

    bleu_df = pd.DataFrame(
        {
            question_id_col: df[question_id_col].values,
            "BLEU": bleu_scores,
            "BLEU_1gram_prec": bleu_1gram_precision,
            "BLEU_2gram_prec": bleu_2gram_precision,
            "BLEU_3gram_prec": bleu_3gram_precision,
            "BLEU_4gram_prec": bleu_4gram_precision,
            "BLEU_BP": bleu_bp,
            "BLEU_sys_len": bleu_sys_len,
            "BLEU_ref_len": bleu_ref_len,
        }
    )

    avg_bleu = bleu_df["BLEU"].mean()
    print(f"Average sentence-level BLEU for {output_csv_path}: {avg_bleu:.2f}")
    print(f"BLEU signature: {bleu_metric.get_signature()}")

    bleu_df.to_csv(output_csv_path, index=False)
    print(f"Saved BLEU results to: {output_csv_path}\n")

    if (
        mean_csv_path is not None
        and os.path.exists(mean_csv_path)
        and dataset_lang is not None
    ):
        mean_eval = pd.read_csv(mean_csv_path)
        if f"BLEU_{dataset_lang}" not in mean_eval["metric"].values:
            mean_eval = pd.concat(
                [
                    mean_eval,
                    pd.DataFrame(
                        [{"metric": f"BLEU_{dataset_lang}", "value": avg_bleu}]
                    ),
                ],
                ignore_index=True,
            )
        mean_eval.to_csv(mean_csv_path, index=False)

    return bleu_df


def run_bleu_eval(config):
    csv_path_de = config.get("csv_path_de")
    mean_csv_path = config.get("csv_path_mean_bleu", None)
    output_csv_de = config.get("output_csv_bleu", None)
    if not csv_path_de or not output_csv_de:
        raise ValueError("csv_path_de and output_csv_bleu must be set in config.")

    df_original_de = pd.read_csv(csv_path_de)
    bleu_df_de = compute_sentence_bleu(
        df=df_original_de,
        reference_col="human_answer",
        hypothesis_col="chatbot_answer",
        question_id_col="question_id_q",
        output_csv_path=output_csv_de,
        mean_csv_path=mean_csv_path,
        dataset_lang="de",
    )
    return bleu_df_de
