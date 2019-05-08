# -*- coding: utf-8 -*-
"""
######################################################
#             2D Heat Conduction Solver              #
#              Created by J. Mark Epps               #
#          Part of Masters Thesis at UW 2018-2020    #
######################################################

This file contains the main executable script for solving 2D conduction:
    -Uses FileClasses.py to read and write input files to get settings for solver
    and geometry
    -Creates a domain class from GeomClasses.py
    -Creates solver class from SolverClasses.py with reference to domain class
    -Can be called from command line with: 
        python main.py [Input file name+extension] [Output directory relative to current directory]
    -Calculates the time taken to run solver
    -Changes boundary conditions based on ignition criteria
    -Saves temperature data (.npy) at intervals defined in input file
    -Saves x,y meshgrid arrays (.npy) to output directory

Features:
    -Ignition condition met, will change north BC to that of right BC
    -Saves temperature and reaction data (.npy) depending on input file 
    settings

"""

##########################################################################
# ----------------------------------Libraries and classes
##########################################################################
import numpy as np
import string as st
#from datetime import datetime
import os
import sys
import time
import copy
from mpi4py import MPI

import GeomClasses as Geom
import SolverClasses as Solvers
import FileClasses
import mpi_routines

##########################################################################
# -------------------------------------Beginning
##########################################################################

comm = MPI.COMM_WORLD
rank = comm.Get_rank()
size = comm.Get_size()

# Print intro on process 0 only
if rank==0:
    print('######################################################')
    print('#             2D Heat Conduction Solver              #')
    print('#              Created by J. Mark Epps               #')
    print('#          Part of Masters Thesis at UW 2018-2020    #')
    print('######################################################\n')
    
    # Start timer
    time_begin=time.time()

# Get arguments to script execution
settings={'MPI_Processes': size}
BCs={}
Sources={}
Species={}
inputargs=sys.argv
if len(inputargs)>2:
    input_file=inputargs[1]
    settings['Output_directory']=inputargs[2]
else:
    if rank==0:
        print 'Usage is: python main.py [Input file] [Output directory]\n'
        print 'where\n'
        print '[Input file] is the name of the input file with extension; must be in current directory'
        print '[Output directory] is the directory to output the data; will create relative to current directory if it does not exist'
        print '***********************************'
    sys.exit('Solver shut down on %i'%(rank))
##########################################################################
# -------------------------------------Read input file
##########################################################################
if rank==0:
    print 'Reading input file...'
fin=FileClasses.FileIn(input_file, 0)
fin.Read_Input(settings, Sources, Species, BCs)
try:
    os.chdir(settings['Output_directory'])
except:
    os.makedirs(settings['Output_directory'])
    os.chdir(settings['Output_directory'])

##########################################################################
# -------------------------------------Initialize solver and domain
##########################################################################
if rank==0:
    print '################################'
    print 'Initializing geometry package...'
domain=Geom.TwoDimDomain(settings, Species, settings['Domain'], rank)
domain.mesh()
vol=domain.CV_vol()
Ax_l,Ax_r,Ay=domain.CV_area()
if rank==0:
    print '################################'
    print 'Initializing MPI and solver...'
    np.save('X', domain.X, False)
    np.save('Y', domain.Y, False)
mpi=mpi_routines.MPI_comms(comm, rank, size, Sources, Species)
err,vol,Ax_l,Ax_r,Ay=mpi.MPI_discretize(domain, vol, Ax_l, Ax_r, Ay)
if err>0:
    sys.exit('Problem discretizing domain into processes')
#print '****Rank: %i, X array: %f, %f'%(rank, np.amin(domain.X[0,:]), np.amax(domain.X[0,:]))
#print '****Rank: %i, X array shape:  '%(rank)+str(np.shape(domain.X))
#print '****Rank: %i, Y array: %f, %f'%(rank, np.amin(domain.Y[:,0]), np.amax(domain.Y[:,0]))
#print '****Rank: %i, Process neighbors(LRTB): %i, %i, %i, %i'%(rank, domain.proc_left, domain.proc_right, domain.proc_top, domain.proc_bottom)
#print '****Rank: %i, vol/Area shapes: '%(rank)+str(vol.shape)+', '+str(Ax_l.shape)+', '+str(Ax_r.shape)
#print '****Rank: %i, process arrangemtn: '%(rank)+str(domain.proc_arrang)
domain.create_var(Species)
solver=Solvers.TwoDimSolver(domain, settings, Sources, copy.deepcopy(BCs), comm)
if rank==0:
    settings['MPI_arrangment']=domain.proc_arrang.copy()
    print '################################'
    print 'Initializing domain...'

time_max='0.000000'
T=300*np.ones_like(domain.E)
# Restart from previous data
if type(settings['Restart']) is int:
    times=os.listdir('.')
    i=len(times)
    if i<2:
        sys.exit('Cannot find a file to restart a simulation with')
    j=0
    while i>j:
        if st.find(times[j],'T')==0 and st.find(times[j],'.npy')>0 \
            and st.find(times[j],str(settings['Restart']))>=0:
            times[j]=st.split(st.split(times[j],'_')[1],'.npy')[0]
#            if st.find(times[j],str(settings['Restart']))>=0:
            time_max=times[j]
            j+=1
            break
        else:
            del times[j]
            i-=1
    T=np.load('T_'+time_max+'.npy')
    if st.find(Sources['Source_Kim'],'True')>=0:
        domain.eta=np.load('eta_'+time_max+'.npy')
    if bool(domain.m_species):
        domain.P=np.load('P_'+time_max+'.npy')
        for i in range(len(Species['Species'])):
            domain.m_species[Species['Species'][i]]=np.load('m_'+Species['Species'][i]+'_'+time_max+'.npy')
            domain.m_0[1:-1,1:-1]+=Species['Specie_IC'][i]
            domain.m_0[1:-1,0] +=0.5*Species['Specie_IC'][i]
            domain.m_0[1:-1,-1]+=0.5*Species['Specie_IC'][i]
            domain.m_0[0,1:-1] +=0.5*Species['Specie_IC'][i]
            domain.m_0[-1,1:-1]+=0.5*Species['Specie_IC'][i]
            domain.m_0[0,0] +=0.25*Species['Specie_IC'][i]
            domain.m_0[0,-1]+=0.25*Species['Specie_IC'][i]
            domain.m_0[-1,0]+=0.25*Species['Specie_IC'][i]
            domain.m_0[-1,-1] +=0.25*Species['Specie_IC'][i]
            
if (bool(domain.m_species)) and (type(settings['Restart']) is str):
    for i in range(len(Species['Species'])):
#        domain.m_species[Species['Species'][i]][:,:]=Species['Specie_IC'][i]
        domain.m_species[Species['Species'][i]][:,:]=Species['Specie_IC'][i]
        domain.m_species[Species['Species'][i]][:,0] *=0.5
        domain.m_species[Species['Species'][i]][:,-1]*=0.5
        domain.m_species[Species['Species'][i]][0,:] *=0.5
        domain.m_species[Species['Species'][i]][-1,:]*=0.5
        domain.m_0+=domain.m_species[Species['Species'][i]] 
k,rho,Cv,D=domain.calcProp(vol)
domain.E=rho*vol*Cv*T
del k,rho,Cv,D,T
##########################################################################
# ------------------------Write Input File settings to output directory
##########################################################################
if rank==0:
    print '################################'
    print 'Saving input file to output directory...'
    #datTime=str(datetime.date(datetime.now()))+'_'+'{:%H%M}'.format(datetime.time(datetime.now()))
    isBinFile=False
    
    input_file=FileClasses.FileOut('Input_file', isBinFile)
    
    # Write header to file
    input_file.header_cond('INPUT')
    
    # Write input file with settings
    input_file.input_writer_cond(settings, Sources, Species, BCs)
    print '################################\n'
    
    print 'Saving data to numpy array files...'
#print '****Rank: %i, first save to numpy files'%(rank)
mpi.save_data(domain, Sources, Species, time_max, vol)

##########################################################################
# -------------------------------------Solve
##########################################################################
t,nt,tign=float(time_max)/1000,0,0 # time, number steps and ignition time initializations
v_0,v_1,v,N=0,0,0,0 # combustion wave speed variables initialization
dy=mpi.compile_var(domain.dY, domain)

# Setup intervals to save data
output_data_t,output_data_nt=0,0
if settings['total_time_steps']=='None':
    output_data_t=settings['total_time']/settings['Number_Data_Output']
    settings['total_time_steps']=settings['total_time']*10**9
    t_inc=int(t/output_data_t)+1
elif settings['total_time']=='None':
    output_data_nt=int(settings['total_time_steps']/settings['Number_Data_Output'])
    settings['total_time']=settings['total_time_steps']*10**9
    t_inc=0

# Ignition conditions
Sources['Ignition']=st.split(Sources['Ignition'], ',')
Sources['Ignition'][1]=float(Sources['Ignition'][1])
BCs_changed=False

if rank==0:
    print 'Solving:'
while nt<settings['total_time_steps'] and t<settings['total_time']:
    # First point in calculating combustion propagation speed
#    T_0=domain.TempFromConserv(vol)
    if st.find(Sources['Source_Kim'],'True')>=0 and BCs_changed:
        eta=mpi.compile_var(domain.eta, domain)
#        v_0=np.sum(eta[:,int(len(domain.eta[0,:])/2)]*dy[:,int(len(domain.eta[0,:])/2)])
        if rank==0:
            v_0=np.sum(eta*dy)/len(eta[0,:])
    
    # Update ghost nodes
    mpi.update_ghosts(domain)
    # Actual solve
    err,dt=solver.Advance_Soln_Cond(nt, t, vol, Ax_l, Ax_r, Ay)
    t+=dt
    nt+=1
    # Check all error codes and send the maximum code to all processes
    err=comm.reduce(err, op=MPI.MAX, root=0)
    err=comm.bcast(err, root=0)
    
    if err>0:
        if rank==0:
            print '#################### Solver aborted #######################'
            print 'Saving data to numpy array files...'
            input_file.Write_single_line('#################### Solver aborted #######################')
            input_file.Write_single_line('Time step %i, Time elapsed=%f, error code=%i;'%(nt,t,err))
            input_file.Write_single_line('Error codes: 1-time step, 2-Energy, 3-reaction progress, 4-Species balance')
        mpi.save_data(domain, Sources, Species, '{:f}'.format(t*1000), vol)
        break
    
    # Output data to numpy files
    if (output_data_nt!=0 and nt%output_data_nt==0) or \
        (output_data_t!=0 and (t>=output_data_t*t_inc and t-dt<output_data_t*t_inc)):
        if rank==0:
            print 'Saving data to numpy array files...'
        mpi.save_data(domain, Sources, Species, '{:f}'.format(t*1000), vol)
        t_inc+=1
        
    # Change boundary conditions
    T=mpi.compile_var(domain.TempFromConserv(vol), domain)
    eta=mpi.compile_var(domain.eta, domain)
    if ((Sources['Ignition'][0]=='eta' and np.amax(eta)>=Sources['Ignition'][1])\
        or (Sources['Ignition'][0]=='Temp' and np.amax(T)>=Sources['Ignition'][1]))\
        and not BCs_changed:
        if domain.proc_top<0:
            solver.BCs.BCs['bc_north_E']=BCs['bc_right_E']
        if rank==0:
            input_file.fout.write('##bc_north_E_new:')
            input_file.Write_single_line(str(solver.BCs.BCs['bc_north_E']))
            input_file.fout.write('\n')
            tign=t
        mpi.save_data(domain, Sources, Species, '{:f}'.format(t*1000), vol)
        BCs_changed=True
        BCs_changed=comm.bcast(BCs_changed, root=0)
        
    # Second point in calculating combustion propagation speed
    if st.find(Sources['Source_Kim'],'True')>=0 and BCs_changed:
        if rank==0:
            v_1=np.sum(eta[:,int(len(eta[0,:])/2)]*dy[:,int(len(eta[0,:])/2)])
    #        v_1=np.sum(eta*dy)/len(eta[0,:])
            if (v_1-v_0)/dt>0.001:
                v+=(v_1-v_0)/dt
                N+=1

if rank==0:
    time_end=time.time()
    input_file.Write_single_line('Final time step size: %f microseconds'%(dt*10**6))
    print 'Ignition time: %f ms'%(tign*1000)
    input_file.Write_single_line('Ignition time: %f ms'%(tign*1000))
    print 'Solver time per 1000 time steps: %f min'%((time_end-time_begin)/60.0*1000/nt)
    input_file.Write_single_line('Solver time per 1000 time steps: %f min'%((time_end-time_begin)/60.0*1000/nt))
    print 'Number of time steps completed: %i'%(nt)
    input_file.Write_single_line('Number of time steps completed: %i'%(nt))
    try:
        print 'Average wave speed: %f m/s'%(v/N)
        input_file.Write_single_line('Average wave speed: %f m/s'%(v/N))
        input_file.close()
    except:
        print 'Average wave speed: 0 m/s'
        input_file.Write_single_line('Average wave speed: 0 m/s')
        input_file.close()
    print('Solver has finished its run')