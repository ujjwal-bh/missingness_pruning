"""Stable serialized preprocessor for the locked flag-removal benchmark."""
from missingness_pruning_inputs import CORE,np
from revised_mimic_models import ClinicalInputs

class PruningInputs(ClinicalInputs):
    def __init__(self,drop_indicators=()):
        super().__init__(CORE)
        self.drop_indicators=drop_indicators
    def fit(self,X,y=None):
        if len(set(self.drop_indicators))!=len(self.drop_indicators) or not set(self.drop_indicators).issubset(CORE):raise ValueError('Invalid explicit indicator names')
        super().fit(X,y)
        self.column_indices_=np.r_[np.arange(len(CORE)),[len(CORE)+j for j,c in enumerate(CORE) if c not in self.drop_indicators]].astype(int)
        return self
    def transform(self,X):return super().transform(X)[:,self.column_indices_]
