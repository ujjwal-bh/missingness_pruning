"""Shared leakage-aware preprocessing, ANN fitting and operating-point metrics."""
from pathlib import Path
import sys,os
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.ann_runtime'));sys.path.insert(0,str(ROOT/'.model_runtime'))
for name in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS']:os.environ.setdefault(name,'2')
import copy,math,random
import numpy as np
import torch
from torch import nn
from sklearn.base import BaseEstimator,TransformerMixin
from sklearn.metrics import average_precision_score,roc_auc_score,brier_score_loss,log_loss
from scipy.special import expit,logit
from scipy.optimize import minimize,brentq

class ClinicalInputs(TransformerMixin,BaseEstimator):
    def __init__(self,features):self.features=features
    def fit(self,X,y=None):
        X=np.asarray(X,dtype=float)
        if np.isinf(X).any() or np.isnan(X).all(axis=0).any():raise ValueError('Invalid fitting inputs')
        self.lower_=np.full(X.shape[1],-np.inf);self.upper_=np.full(X.shape[1],np.inf)
        for j,name in enumerate(self.features):
            if name not in ['age_capped_90','female']:self.lower_[j],self.upper_[j]=np.nanquantile(X[:,j],[.005,.995])
        capped=np.clip(X,self.lower_,self.upper_);self.median_=np.nanmedian(capped,axis=0)
        filled=np.where(np.isnan(capped),self.median_,capped)
        self.mean_=filled.mean(axis=0);self.scale_=filled.std(axis=0);self.scale_[self.scale_==0]=1
        return self
    def transform(self,X):
        X=np.asarray(X,dtype=float)
        if X.shape[1]!=len(self.features) or np.isinf(X).any():raise ValueError('Input shape/nonfinite mismatch')
        missing=np.isnan(X);capped=np.clip(X,self.lower_,self.upper_)
        filled=np.where(missing,self.median_,capped)
        return np.concatenate([(filled-self.mean_)/self.scale_,missing.astype(float)],axis=1)

class MortalityANN(nn.Module):
    def __init__(self,inputs=52,dropout=0.,batchnorm=False):
        super().__init__();layers=[]
        for a,b in [(inputs,64),(64,32)]:
            layers.append(nn.Linear(a,b))
            if batchnorm:layers.append(nn.BatchNorm1d(b,track_running_stats=True))
            layers.append(nn.ReLU())
            if dropout:layers.append(nn.Dropout(dropout))
        layers.append(nn.Linear(32,1));self.network=nn.Sequential(*layers)
    def forward(self,x):return self.network(x).squeeze(-1)

def seed_all(seed):
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)

def predict_ann(model,X):
    previous=model.training;model.eval();pieces=[]
    with torch.inference_mode():
        for chunk in torch.as_tensor(np.asarray(X,dtype=np.float32)).split(8192):pieces.append(torch.sigmoid(model(chunk)).numpy())
    model.train(previous)
    return np.concatenate(pieces).astype(float)

def fit_ann(X,y,config,seed,stop=None,epochs=None):
    seed_all(seed)
    model=MortalityANN(X.shape[1],config['dropout'],config['batchnorm'])
    optimizer=torch.optim.AdamW(model.parameters(),lr=config['lr'],weight_decay=config['weight_decay'])
    tx=torch.as_tensor(np.asarray(X,dtype=np.float32));ty=torch.as_tensor(np.asarray(y,dtype=np.float32))
    weight=float(config['death_weight']);pw=torch.tensor(weight,dtype=torch.float32)
    generator=torch.Generator().manual_seed(seed+100)
    best=-np.inf;best_state=None;best_epoch=0;stale=0;trace=[]
    maximum=int(epochs) if epochs is not None else 100
    for epoch in range(1,maximum+1):
        model.train();order=torch.randperm(len(tx),generator=generator);loss_sum=denom_sum=0.
        for ids in torch.tensor_split(order,max(1,math.ceil(len(tx)/1024))):
            optimizer.zero_grad(set_to_none=True);target=ty[ids]
            loss=torch.nn.functional.binary_cross_entropy_with_logits(model(tx[ids]),target,pos_weight=pw,reduction='sum')
            denom=(1+(weight-1)*target).sum();normalized=loss/denom
            if not torch.isfinite(normalized):raise FloatingPointError('Nonfinite ANN loss')
            normalized.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),5.);optimizer.step()
            loss_sum+=float(loss.detach());denom_sum+=float(denom)
        row={'epoch':epoch,'weighted_training_loss':loss_sum/denom_sum}
        if stop is not None:
            score=float(average_precision_score(stop[1],predict_ann(model,stop[0])));row['stopping_AP']=score
            if score>best+.0001:
                best=score;best_epoch=epoch;best_state=copy.deepcopy(model.state_dict());stale=0
            else:stale+=1
        trace.append(row)
        if stop is not None and stale>=10:break
    if stop is not None:
        if best_state is None:raise RuntimeError('No valid stopping checkpoint')
        model.load_state_dict(best_state)
    else:best_epoch=maximum
    model.eval()
    return model,best_epoch,trace

def threshold_for_recall(y,p,target=.7):
    y=np.asarray(y);p=np.asarray(p,dtype=float)
    if not 0<target<=1 or len(y)!=len(p) or not np.isfinite(p).all():raise ValueError('Invalid operating point inputs')
    deaths=np.sort(p[y==1])[::-1]
    if not len(deaths):raise ValueError('No deaths')
    return float(deaths[math.ceil(target*len(deaths))-1])

def classification(y,p,t):
    y=np.asarray(y,dtype=int);positive=np.asarray(p)>=t
    tp=int(((y==1)&positive).sum());fp=int(((y==0)&positive).sum())
    tn=int(((y==0)&~positive).sum());fn=int(((y==1)&~positive).sum())
    return {'threshold':float(t),'TP':tp,'FP':fp,'TN':tn,'FN':fn,
        'recall_percent':100*tp/(tp+fn),'precision_percent':100*tp/(tp+fp) if tp+fp else 0.,
        'F1_percent':100*2*tp/(2*tp+fp+fn),'specificity_percent':100*tn/(tn+fp),
        'FPR_percent':100*fp/(tn+fp),'accuracy_percent':100*(tp+tn)/len(y),'alerts_percent':100*(tp+fp)/len(y)}

def metrics(y,p):
    y=np.asarray(y,dtype=int);p=np.asarray(p,dtype=float);z=logit(np.clip(p,1e-7,1-1e-7))
    def loss(b):return np.mean(np.logaddexp(0,b[0]+b[1]*z)-y*(b[0]+b[1]*z))
    def grad(b):
        delta=expit(b[0]+b[1]*z)-y
        return [delta.mean(),np.mean(delta*z)]
    fit=minimize(loss,[0.,1.],jac=grad,method='BFGS',options={'maxiter':1000,'gtol':1e-7})
    return {'patients':len(y),'deaths':int(y.sum()),'observed_mortality':float(y.mean()),
        'AUROC':float(roc_auc_score(y,p)),'average_precision':float(average_precision_score(y,p)),
        'Brier':float(brier_score_loss(y,p)),'log_loss':float(log_loss(y,p,labels=[0,1])),
        'mean_prediction':float(p.mean()),'calibration_slope':float(fit.x[1]),
        'calibration_intercept_joint':float(fit.x[0]),'calibration_diagnostic_converged':bool(fit.success),
        'calibration_in_large':float(brentq(lambda b:expit(z+b).mean()-y.mean(),-100,100))}
