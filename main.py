import torch
import pandas as pd
from transformer import *
from dataloading import *
from timeit import default_timer as timer

device = torch.device('mps')
torch.manual_seed(1337)
torch.mps.set_per_process_memory_fraction(0.0)

batch_size = 512
src_tokens = []
tgt_tokens = []
src_stoi_vocab = {'<pad>': 0, '[start]': 1, '[end]': 2} 
src_itos_vocab = {0:'<pad>', 1:'[start]', 2:'[end]'}
tgt_stoi_vocab = {'<pad>': 0, '[start]': 1, '[end]': 2}
tgt_itos_vocab = {0:'<pad>', 1:'[start]', 2:'[end]'}

df_src = pd.read_csv("./small_vocab_en.csv", sep='\t', header = None)
df_src = df_src.rename(columns={0:"src"})

df_tgt = pd.read_csv('./small_vocab_fr.csv', sep='\t', header = None)
df_tgt = df_tgt.rename(columns={0:"tgt"})

df = pd.concat([df_src, df_tgt], axis=1)
df = df.sample(frac=1, random_state=42)
print("Sample Data")
print("Source Language\t\t\t\t\t\t\t\tTarget Language")

print_sample_data(df, sample=5)

print("Total Number of Sentences: {0}".format(len(df_src)))

df['src'] = df['src'].apply(lambda text: clean_prepare_text(text))
df['tgt'] = df['tgt'].apply(lambda text: clean_prepare_text(text))

df['src'].apply(lambda text: create_vocab(text, src_stoi_vocab, src_itos_vocab))
df['tgt'].apply(lambda text: create_vocab(text, tgt_stoi_vocab, tgt_itos_vocab))

src_vocab_size, tgt_vocab_size = len(src_stoi_vocab), len(tgt_stoi_vocab)
print("Source Vocab Size is {0} and Target Vocab Size is {1}".format(src_vocab_size, tgt_vocab_size))

# encode sentences into tokens
print("Encoding Sentences into tokens")
for src_sent, tgt_sent in zip(df['src'], df['tgt']):
    src_tokens.append(tokenize_sentence(src_sent, src_stoi_vocab))
    tgt_tokens.append(tokenize_sentence(tgt_sent, tgt_stoi_vocab))

max_seq_length = max([max(len(src_token), len(tgt_token)) for src_token, tgt_token in zip(src_tokens, tgt_tokens)])
print("Maximum Sequence Length: {}".format(max_seq_length))

# create train-val-test split
train_ratio = 0.8
val_ratio = 0.1
test_ratio = 0.1

num_sentences = len(df)
num_train = int(train_ratio * num_sentences)
num_val = int(val_ratio * num_sentences)
num_test = num_sentences - num_train - num_val

train_src_tokens, train_tgt_tokens = src_tokens[:num_train], tgt_tokens[:num_train]
val_src_tokens, val_tgt_tokens = src_tokens[num_train:num_train+num_val], tgt_tokens[num_train:num_train+num_val]
test_src_tokens, test_tgt_tokens = src_tokens[num_train+num_val:], tgt_tokens[num_train+num_val:]

train_dataset = TranslationDataset(train_src_tokens, train_tgt_tokens, max_len=max_seq_length)
val_dataset = TranslationDataset(val_src_tokens, val_tgt_tokens, max_len=max_seq_length)
test_dataset = TranslationDataset(test_src_tokens, test_tgt_tokens, max_len=max_seq_length)

train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
val_loader = torch.utils.data.DataLoader(val_dataset, batch_size=batch_size)
test_loader = torch.utils.data.DataLoader(test_dataset, batch_size=1)

model = Transformer(embd_sze=512, src_vocab_sze=src_vocab_size, tgt_vocab_sze=tgt_vocab_size, max_seq_len=max_seq_length)
model.to(device)
#model.load_state_dict(torch.load("./model.pt", weights_only=True))
print("Number of parameters: {} M".format(sum(p.numel() for p in model.parameters())/1e6))

optimizer = torch.optim.Adam(model.parameters(), lr=1e-4)
loss_func = torch.nn.CrossEntropyLoss().to(device)
epochs = 2

# model training
for epoch in range(1, epochs+1):
    start_time = timer()
    train_loss = 0
    model.train()
    # train loop
    for i, (src, tgt) in enumerate(train_loader):
        src, tgt = src.to(device), tgt.to(device)

        tgt_input = tgt[:, :-1]
        tgt_output = tgt[:, 1:]

        src_mask, tgt_mask = make_mask(src, tgt_input, src_stoi_vocab, tgt_stoi_vocab, device)

        # zero out gradients before every batch
        optimizer.zero_grad()

        # forward pass
        e_output = model.encode(src, src_mask)
        output = model.decode(tgt_input, e_output, src_mask, tgt_mask)

        # calculate loss
        loss = loss_func(output.view(-1, output.size(-1)), tgt_output.reshape(tgt_output.shape[0] * tgt_output.shape[1]))
        # backward pass
        loss.backward()

        # gradient descent
        optimizer.step()
        train_loss += loss.item()

    # valdition loop
    val_loss = 0
    model.eval()
    with torch.no_grad():
        for i, (src, tgt) in enumerate(val_loader):
            src, tgt = src.to(device), tgt.to(device)
            tgt_input = tgt[:, :-1]
            tgt_output = tgt[:, 1:]

            src_mask, tgt_mask = make_mask(src, tgt_input, src_stoi_vocab, tgt_stoi_vocab, device)

            # zero out gradients before every batch
            optimizer.zero_grad()

            # forward pass
            e_output = model.encode(src, src_mask)
            output = model.decode(tgt_input, e_output, src_mask, tgt_mask)

            # calculate loss
            loss = loss_func(output.view(-1, output.size(-1)), tgt_output.reshape(tgt_output.shape[0] * tgt_output.shape[1]))
            
            val_loss += loss.item()
    end_time = timer()

    print("Epoch: {0} | Training Loss: {1} | Validation Loss: {2} | Epoch Time: {3}s".\
          format(epoch, round(train_loss/len(train_loader), 4), round(val_loss / len(val_loader), 4), round(end_time-start_time, 4)))

torch.save(model.state_dict(), "./model.pt")