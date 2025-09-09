import pandas as pd
import parameters

# Extract the list of parvalues
parvalue_list = parameters.parameters["parvalue"]

# Convert to DataFrame
df = pd.DataFrame(parvalue_list)

# Export to Excel
df.to_excel("parvalue_export.xlsx", index=False)

print("Exported parvalue to parvalue_export.xlsx")