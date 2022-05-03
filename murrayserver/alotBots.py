# I have copied across a set of participant IDs from the human-human data to test the concept.
# In practice, we would just apply the 'condition_allocation(participantID)' function as each new participant signs in to the study then feed the output [0-5, 0-5] into the game and bot-type


import matplotlib.pyplot as plt
from collections import Counter
import numpy as np
from time import sleep

show_fig = False
# pIDs = ['610421096c1af729ade5aac1',
#     '5a84f454ae9a0b0001a9e4e5',
#     '604fa685e33606f9a0ee8189',
#     '61017941304cf7ac38c2e110',
#     '61017941304cf7ac38c2e110',
#     '5c5cad3e4ee81200018eafe2',
#     '60fd56db5fe37ebeca00bc83',
#     '5eb05ee34ca8a81042c289ab',
#     '615ddab1e4f013092538b6c5',
#     '5c2b4b959f18a9000179a141',
#     '6171809ed83c5413d1594bfc',	
#     '6103e8f96b5ce82b76f85e05',
#     '5ee91869ec57d2169fca4494',	
#     '5f27f163a848900559c65ec2',
#     '5e762510b2dbac0009c68dd7',	
#     '616e7e77bab9e87f4598a9a8',
#     '60d7bf526fa720789404dbb0',	
#     '6169d9866cc7e44241cfc688',
#     '615f4485ee8fcad69ef8d38b',	
#     '60fdddd7a026e966c556be13',
#     '5ae959f4b7798500019260ad',	
#     '5968c58012e7f700013b4acc',
#     '61518742af2f6094e92bace1',	
#     '577e3a5025cb71000128727e',
#     '5cd139c62ce2410014540d4d',
#     '5e3056fa23a9e80286bbb370',
#     '615b11e154e31480eaf1b78a',
#     '6166c2849af8d8e1858e3b14',
#     '61680035775d6be6c3034464',
#     '61548c8901c5c2a2fb997763',
#     '616047aca593ff6eb34c2bb3',
#     '615a0198a1a2d449a781b8a5',
#     '61542508e4600733844ab8af',
#     '59d4283121977e0001d62f46',
#     '5e46d130954b011968fcc862',
#     '59d4283121977e0001d62f46',
#     '5fa84432f643c7686ab96927',
#     '616410529bf3660626527235',
#     '6160c92e9027d2e219dc975a',
#     '616d823fbceeadebef2c2923',
#     '615afc4b6a313ec070c76d4c',
#     '6148beccb767e62c451ce7bc',
#     '6154e0eaaaa79b827af4bca6',
#     '5a8ff02e4fcb2f0001d8bb9b',
#     '60fd18e34ebe98b059adf020',
#     '5e4344c1c3e7db1e29935599',
#     '614cf7d1df2213f8c1f81e6e',
#     '615a17c90199096a5bbe0f48',
#     '6134bc3c8e266fcf6ba97739',
#     '5e779837e8230d2ffd8717b1',
#     '5e779837e8230d2ffd8717b1',
#     '5e35373e1ddb124e6c306747',
#     '6153593be7f8925dee8d7db6',
#     '59c10c7e5364260001dc47e6'
#     '6148ee933093eb6be1edf761',
#     '613a2a827cab4afeb484eef1',
#     '615c29d30804319d32d20351',
#     '5929e024943e670001cde06b',
#     '614881481dcfc1e2ea215aca',
#     '6160717242827a64a55d99ad',
#     '6151c7989b3c460fe4400daa',
#     '615f45e5c7d52a87e60831d7',
#     '6163f8a826c9b98b20139416',
#  ]
 
# def condition_allocation(pID):
#     bot_condition   = []
#     block_order     = []
#     n_bot_types     =  6
#     n_blocks        = 6
#     for character in pID:
#         try: # arbitrarily, use the random numbers to determine block_order
#             block_order.append(int(character))
#         except: # and use the random characters to determine bot_type
#             bot_condition.append(ord(character))
#     return [sum(block_order)%n_blocks, sum(bot_condition)%n_bot_types]

# allocations = []
# for pid in pIDs:
#     allocations.append(condition_allocation(pid))
# print(len(allocations), allocations)

final_allocations = np.zeros((6,6))
f_a = np.zeros((6,6))
game_allocations = []
# for i, ii in allocations:
#     final_allocations[i,ii] += 1
# print(final_allocations)

completed_game_nos = [0,
7,
14,
21,
28,
35,
36,
43,
50,
57,
64,
71,
72,
79,
86,
93,
107,
108,
115,
122,
129,
143,
151,
165,
]

ids = range(288)
ids = list(filter(lambda id: id not in completed_game_nos, range(5)))
gn = 0
for game_no in range(10):
    try:
        a = ids.pop(0)
        print([a, gn])
    except:
        a = gn
        print([gn,a])
    
    gn += 1


    # if game_no in ids:#completed_game_nos:
    #     print(f"skipped game number {game_no}")
    #     continue

    bo = game_no%6
    bt = (game_no//6)%6
    
    # bt2= (game_no%6)
    final_allocations[bo,bt] += 1
    game_allocations.append([game_no, bo, bt, int(final_allocations[bo,bt])])

    
    

    print(f'bot order = {bo} and bot type = {bt}')
    sleep(1)

# np.savetxt('game_allocations.csv',game_allocations,delimiter=',',fmt='%d',header ="game_no, block_order, bot_type, n_games")

if show_fig:
    plt.imshow(final_allocations,cmap='coolwarm',interpolation='nearest',extent=(0,6,6,0))
    plt.colorbar()

    plt.yticks(ticks=np.arange(6),labels=['A','B','C','D','E','F'])
    plt.ylabel('Block Orders')
    plt.xticks(ticks=np.arange(6), labels=['Dumb-Ambig','Dumb-Hum','Col-Ambig','Col-Hum','Q-Ambig','Q-Hum'],rotation=30)
    plt.xlabel('Bot Types')

    plt.grid(linewidth=2,color='w')

    plt.show()