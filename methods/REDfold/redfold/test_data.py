#! /usr/bin/python3

import numpy as np
import subprocess
import collections
import random
import time
import sys
import os

from .data import *
from .fold import *
from .fold.config import process_config
from .fold.postprocess import postprocess_new as postprocess
from shutil import copyfile


#from network import FCDenseNet as Model
from torch.utils.data import DataLoader
from torch.autograd import Variable
from operator import add
from .dense import FCDenseNet
from .fold.data_generator import RNASSDataGenerator, Dataset
from .fold.data_generator import Dataset_Cut_concat_new_canonicle as Dataset_FCN



def get_seq(contact):
    seq = None
    seq = torch.mul(contact.argmax(axis=1), contact.sum(axis = 1).clamp_max(1))
    seq[contact.sum(axis = 1) == 0] = -1
    return seq

def seq2dot(seq):
    idx = np.arange(1, len(seq) + 1)
    dot_file = np.array(['_'] * len(seq))
    dot_file[seq > idx] = '('
    dot_file[seq < idx] = ')'
    dot_file[seq == 0] = '.'
    dot_file = ''.join(dot_file)
    return dot_file

def seqout(y1,L1,seqhot):

  seq1=""
  fast=""
  y1= y1.float()

  for a1 in range(L1):
    Id1= np.nonzero(seqhot[0,a1]).item()
    seq1+=BASE1[Id1]

    Id2= np.nonzero(y1[0,a1,:L1])
    if (Id2.nelement()):
      fast+= '(' if (a1<Id2) else ')'
    else:
      fast+='.'
  seq1+="\n";

  print(seq1+fast)

#  end seq1+fast

def get_ct_dict(predict_matrix,batch_num,ct_dict):
    
    for i in range(0, predict_matrix.shape[1]):
        for j in range(0, predict_matrix.shape[1]):
            if predict_matrix[:,i,j] == 1:
                if batch_num in ct_dict.keys():
                    ct_dict[batch_num] = ct_dict[batch_num] + [(i,j)]
                else:
                    ct_dict[batch_num] = [(i,j)]
    return ct_dict
    
def get_ct_dict_fast(predict_matrix,batch_num,ct_dict,dot_file_dict,seq_embedding,seq_name):
    seq_tmp = torch.mul(predict_matrix.cpu().argmax(axis=1), predict_matrix.cpu().sum(axis = 1).clamp_max(1)).numpy().astype(int)
    seq_tmp[predict_matrix.cpu().sum(axis = 1) == 0] = -1
    #seq = (torch.mul(predict_matrix.cpu().argmax(axis=1), predict_matrix.cpu().sum(axis = 1)).numpy().astype(int).reshape(predict_matrix.shape[-1]), torch.arange(predict_matrix.shape[-1]).numpy())
    dot_list = seq2dot((seq_tmp+1).squeeze())
    seq = ((seq_tmp+1).squeeze(),torch.arange(predict_matrix.shape[-1]).numpy()+1)
    letter='AUCG'
    ct_dict[batch_num] = [(seq[0][i],seq[1][i]) for i in np.arange(len(seq[0])) if seq[0][i] != 0]	
    seq_letter=''.join([letter[item] for item in np.nonzero(seq_embedding)[:,1]])
    dot_file_dict[batch_num] = [(seq_name,seq_letter,dot_list[:len(seq_letter)])]
    return ct_dict,dot_file_dict
# randomly select one sample from the test set and perform the evaluation







def test_data(args,file_config):

  #-Initial
  torch.multiprocessing.set_sharing_strategy('file_system')
#  config_file= args.config
  config= process_config(file_config)
  Use_gpu= torch.cuda.is_available()


  #-parameter
  batch_n= config.batch_size_stage_1
  test_data= config.test_data
  data_type= config.data_type
  model_type= config.model_type
  epoch_n= config.epoches_first
  set_gamma= config.set_gamma
  set_rho= set_gamma+0.1
  set_L1= config.set_L1

  flag_train= args.train
  flag_load= config.load_model or not args.train
  
  fhead1= data_type
  file1= f"{fhead1}/{model_type}.pt"

  if not os.path.exists(fhead1):
    os.mkdir(fhead1)

  if not os.path.exists(file1):
    try:
      copyfile(redfold_path+f'/{model_type}.pt', file1)
    except:
      raise SystemExit('error: Fail in model path!')


  #positive set balance weight for loos function
  #loss_weight= torch.Tensor([300]).cuda()
  loss_weight= torch.Tensor([300])#.cuda()



#  test_files= args.test_files[0]
  test_files= f"{fhead1}/{test_data}.pick"

  #print('Loading file: ',test_files)


  #-Load Dataset
#  test_data= RNADataset(test_files,720)
  test_data= RNASSDataGenerator(test_files,720)

  test_len= len(test_data)
  #print("Loading dataset Done!!!")
  #print(f"train.len={test_len}")
  test_set= Dataset_FCN(test_data)

  
  dataloader= DataLoader(dataset=test_set, batch_size=batch_n, shuffle=1, num_workers=12)

  #- Network
  model= FCDenseNet(in_channels=146,out_channels=1,
                    initial_num_features=16,
                    dropout=0,

                    down_dense_growth_rates=(4,8,16,32),
                    down_dense_bottleneck_ratios=None,
                    down_dense_num_layers=(4,4,4,4),
                    down_transition_compression_factors=1.0,

                    middle_dense_growth_rate=32,
                    middle_dense_bottleneck=None,
                    middle_dense_num_layers=8,

                    up_dense_growth_rates=(64,32,16,8),
                    up_dense_bottleneck_ratios=None,
                    up_dense_num_layers=(4,4,4,4))
        

  # Model on GPU
  if Use_gpu:
    model= model.cuda()

  #print(model)



#  loss_f= torch.nn.BCEWithLogitsLoss(pos_weight= torch.Tensor(loss_weight).cuda())
  loss_f= torch.nn.BCEWithLogitsLoss(pos_weight= loss_weight)
#  loss_f= torch.nn.CrossEntropyLoss()
#  optimizer= torch.optim.Adam(model.parameters(),lr=learn_rate)
  optimizer= torch.optim.Adam(model.parameters())


  if flag_load:
    #mod_state= torch.load(file1)
    mod_state= torch.load(file1, map_location=torch.device('cpu'))
    model.load_state_dict(mod_state['state_dict'])
    epoch1= mod_state['epoch']
    
  if not (flag_load and flag_train):
    epoch1= 0

  if flag_train:
    phase= "train"
    epoch2= epoch1+epoch_n
  else:
    phase= "test"
    epoch2= epoch1+1



  for epoch in range(epoch1,epoch2):

    running_loss= 0
    running_correct= 0
    #print(f"-"*10)
    #print(f"Epoch {epoch}/{epoch2}")
    #print(f"-"*10)
    #print(f"Phase {phase}...")

    model.train()
        
    #print(f"Train data:{len(dataloader)}")
  

    for [x1, y1, L1, seq_hot,seq_name] in dataloader:


      # Data on GPU
      if Use_gpu:
        x1= x1.cuda().type(torch.cuda.FloatTensor)
        y1= y1.cuda().type(torch.cuda.FloatTensor)

      [x1, y1]= Variable(x1), Variable(y1)


      if flag_train:
        y_pred= model(x1)
        # Mask Matrix
        mask1= torch.zeros_like(y_pred)
        mask1[:, :L1,:L1] = 1

        y_mask= y_pred*mask1;
        
        # Apply max index along axis=1, and then output index as pred
        # [_,pred]= torch.max(y_pred.data,1)
        optimizer.zero_grad()
        loss= loss_f(y_mask, y1)
        
        loss.backward()
        optimizer.step()
  
  
      else:      
        with torch.no_grad():
          #y_pred= model(x1)
          y_pred= model(x1.type(torch.FloatTensor))

        # post-processing without learning train
        #seq_hot=seq_hot.cuda()
        y_mask= postprocess(y_pred,seq_hot,L1, 0.01, 0.1, 100, set_rho,set_L1,set_gamma)
        optimizer.zero_grad()
        loss= loss_f(y_mask, y1)

        #print(f"\n>{seq_name[0]}")
        print(f">{seq_name[0]}")
        seqout(y_mask>0.5,L1,seq_hot)

      
      running_loss+= loss.data


    epoch_loss= running_loss*batch_n/test_len
    #print(f"Epoch Loss:{epoch_loss:.4f}")

  # Save model
  if flag_train:
    file2=f"{data_type}/{model_type}_{epoch+1:03d}.pt"
    #print(f"Saving model to {file2}")


    mod_state= {'epoch': epoch+1, 'state_dict': model.state_dict()}
    torch.save(mod_state,file2);
  #print(f"{phase} finish.")


if __name__=='__main__':

  try:
    args= get_args()
  except IndexError as ie:
    print(f"Warning: {ie}")


