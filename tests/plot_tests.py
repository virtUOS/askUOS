import matplotlib.pyplot as plt


def plot_result(
    values, filename="plot.png", title="List Plot", x_label="Index", y_label="Value"
):
    """
    Plots a list of numerical values using Matplotlib and saves the plot as a PNG file.

    Parameters:
    - values: List of numerical values to plot.
    - filename: Name of the file where the plot will be saved (with .png extension).
    - title: Title of the plot.
    - x_label: Label for the x-axis.
    - y_label: Label for the y-axis.
    """
    # Check if the input list is empty
    if not values:
        print("Error: The list is empty.")
        return

    # Generate an index array for the x-axis
    indices = list(range(len(values)))

    # Create the plot
    plt.figure(figsize=(10, 5))
    plt.plot(indices, values, marker="o", linestyle="-", color="b")

    # Adding titles and labels
    plt.title(title)
    plt.xlabel(x_label)
    plt.ylabel(y_label)

    # Show grid
    plt.grid()

    # Save the plot as a PNG file
    plt.savefig(filename, format="png")

    # Optionally, close the plot to free memory
    plt.close()

    print(f"Plot saved as {filename}")


# Example usage
if __name__ == "__main__":
    example_list = [1, 3, 5, 7, 9, 3, 6, 8, 10]
    plot_result(
        example_list,
        filename="example_plot.png",
        title="Example List Plot",
        x_label="Index",
        y_label="Value",
    )
