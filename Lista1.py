#1
def func1(x,y):
    if(len(x) > 0):
        if(x[0] == y):
            return func1(x[1:],y) + 1
        return func1(x[1:],y)
    return 0

#2
def func2(x):
    if(len(x) > 0):
        return x[:(len(x)/2)], x[(len(x)/2):] 
       

 #3
def func3(lista):
   def funcaoA(lista1,lista2):
      if(maior(lista1,lista1[0]) > menor(lista2,lista2[0])):
         lista1[pos(lista1,maior(lista1,lista1[0]))], lista2[pos(lista2,menor(lista2,lista2[0]))] = lista2[pos(lista2,menor(lista2,lista2[0]))],lista1[pos(lista1,maior(lista1,lista1[0]))]
         funcaoA(lista1,lista2)
      return lista1,lista2

   def maior(lista1,c):#Metodo que retorna o maior valor de uma lista
      if(len(lista1) > 1):
         if(lista1[1] > c):
            return maior(lista1[1:],lista1[1])
         else:
            return maior(lista1[1:],c)
      return c

   def menor(lista1,c):#Metodo que retorna o menor valor de uma lista
      if(len(lista1) > 1):
         if(lista1[1] < c):
            return menor(lista1[1:],lista1[1])
         else:
            return menor(lista1[1:],c)
      return c

   def pos(lista,n):#Metodo que busca a posicao de um elemento
      if(lista[0] == n):
         return 0
      else:
         return pos(lista[1:],n) + 1
   return funcaoA(lista[:len(lista)/2],lista[len(lista)/2:])


# 4
def func4(lista,x):
    print lista
    def funcao(l,x):
       if(len(l) > 0):
        if(l[0] > x):
            return 0
        else:
            return funcao(l[1:], x) + 1
       else:
           return 0
    lista = ordenar(lista)
    return lista[:funcao(lista,x)],lista[funcao(lista,x):]



def ordenar(l):
    def menor(lista1, c):  # Metodo que retorna o menor valor de uma lista
        if (len(lista1) > 1):
            if (lista1[1] < c):
                return menor(lista1[1:], lista1[1])
            else:
                return menor(lista1[1:], c)
        return c

    def pos(lista, n):  # Metodo que busca a posicao de um elemento
        if (lista[0] == n):
            return 0
        else:
            return pos(lista[1:], n) + 1
    if(len(l) > 0):
        return [l.pop(pos(l,menor(l,l[0])))] + ordenar(l)
    return []

#5   
def func5(l1,l2):
    def menor(lista1, c):  # Metodo que retorna o menor valor de uma lista
        if (len(lista1) > 1):
            if (lista1[1] < c):
                return menor(lista1[1:], lista1[1])
            else:
                return menor(lista1[1:], c)
        return c
    def pos(lista, n):  # Metodo que busca a posicao de um elemento
        if (lista[0] == n):
            return 0
        else:
            return pos(lista[1:], n) + 1
    def juntar(l1,l2,l3):
        if(len(l1) and len(l2) > 0):
            if(menor(l1,l1[0]) >= menor(l2,l2[0])):
                l3.append(menor(l2,l2[0]))
                del l2[pos(l2,menor(l2,l2[0]))]
                return juntar(l1,l2,l3)
            else:
                l3.append(menor(l1, l1[0]))
                del l1[pos(l1, menor(l1, l1[0]))]
                return juntar(l1, l2, l3)
        elif(len(l1) > 0):
            l3.append(menor(l1,l1[0]))
            del l1[pos(l1,menor(l1,l1[0]))]
            return juntar(l1,l2,l3)
        elif(len(l2) > 0):
            l3.append(menor(l2,l2[0]))
            del l2[pos(l2,menor(l2,l2[0]))]
            return juntar(l1,l2,l3)
        else:
            return l3
    return juntar(l1,l2,[])
      
#6   
def func6(l):
    if (len(l) > 0):
        if(func1(l,l[0]) > 1):
            return func6(l[1:])
        else:
            return [l[0]] + func6(l[1:])
    return []

            

if __name__== "__main__":
    
  #  print func1("Khennedy", "K")
    
   # print func2([1,22,3,4,5])
    
   # print func3([3,7,9,1])
    
 print func4([3,7,2,9],7)

  #  print ordenar([1,3,5,1245,24,53,53,2])
 #   print func5([1,3,5],[2,4,6])

    #print func6([1,3,4,1])
