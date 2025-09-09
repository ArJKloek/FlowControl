import pandas as pd
import parameters

# Extract the list of parameters
param_list = parameters.parameters["allparameters"]

# Convert to DataFrame
df = pd.DataFrame(param_list)

# Export to Excel
df.to_excel("parameters_export.xlsx", index=False)

print("Exported parameters to parameters_export.xlsx")