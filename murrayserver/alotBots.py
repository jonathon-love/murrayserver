# I have copied across a set of participant IDs from the human-human data to test the concept.
# In practice, we would just apply the 'condition_allocation(participantID)' function as each new participant signs in to the study then feed the output [0-5, 0-5] into the game and bot-type


import matplotlib.pyplot as plt
from collections import Counter
import numpy as np

pIDs = ['610421096c1af729ade5aac1',
    '5a84f454ae9a0b0001a9e4e5',
    '604fa685e33606f9a0ee8189',
    '61017941304cf7ac38c2e110',
    '61017941304cf7ac38c2e110',
    '5c5cad3e4ee81200018eafe2',
    '60fd56db5fe37ebeca00bc83',
    '5eb05ee34ca8a81042c289ab',
    '615ddab1e4f013092538b6c5',
    '5c2b4b959f18a9000179a141',
    '6171809ed83c5413d1594bfc',	
    '6103e8f96b5ce82b76f85e05',
    '5ee91869ec57d2169fca4494',	
    '5f27f163a848900559c65ec2',
    '5e762510b2dbac0009c68dd7',	
    '616e7e77bab9e87f4598a9a8',
    '60d7bf526fa720789404dbb0',	
    '6169d9866cc7e44241cfc688',
    '615f4485ee8fcad69ef8d38b',	
    '60fdddd7a026e966c556be13',
    '5ae959f4b7798500019260ad',	
    '5968c58012e7f700013b4acc',
    '61518742af2f6094e92bace1',	
    '577e3a5025cb71000128727e',
    '5cd139c62ce2410014540d4d',
    '5e3056fa23a9e80286bbb370'
 ]
 
def condition_allocation(pID):
    bot_condition   = []
    block_order     = []
    n_bot_types     =  6
    n_blocks        = 6
    for character in pID:
        try: # arbitrarily, use the random numbers to determine block_order
            block_order.append(int(character))
        except: # and use the random characters to determine bot_type
            bot_condition.append(ord(character))
    return [sum(block_order)%n_blocks, sum(bot_condition)%n_bot_types]

allocations = []
for pid in pIDs:
    allocations.append(condition_allocation(pid))
print(allocations)

final_allocations = np.zeros((6,6))
for i, ii in allocations:
    final_allocations[i,ii] += 1
print(final_allocations)

# Gotta graph something. It'd be wrong to stuff around with this for the whole morning and NOT make a graph.
plt.imshow(final_allocations,cmap='coolwarm',interpolation='nearest',extent=(0,6,6,0))
plt.colorbar()

plt.yticks(ticks=np.arange(6),labels=['A','B','C','D','E','F'])
plt.ylabel('Block Orders')
plt.xticks(ticks=np.arange(6), labels=['Dumb-Ambig','Dumb-Hum','Col-Ambig','Col-Hum','Q-Ambig','Q-Hum'],rotation=30)
plt.xlabel('Bot Types')

plt.grid(linewidth=2,color='w')

plt.show()

