from hardware import Memory, RegisterFile, Register, MUX_2_1, ALU_32, AND_2
import utilities 
from signals import Signals

class Core_SC: 
    def __init__(self):
        self.I_Mem = Memory()
        self.D_Mem = Memory()
        self.RF = RegisterFile()
        self.RegPC = Register()
        self.signals = Signals()
        self.cycle_num = 0
        self.mode = 0

    def set_PC(self, pc):
        self.RegPC.set_data(pc)
        self.RegPC.set_write(1)

    def set_mode(self, mode):
        self.mode = mode

    def run(self, n_cycles):
        i_cycles = 0
        ending_PC = self.I_Mem.get_ending_address() 

        self.I_Mem.set_memread(1)
        self.I_Mem.set_memwrite(0)

        while (n_cycles == 0 or i_cycles < n_cycles):
            i_cycles += 1
            self.cycle_num += 1
            if ((self.mode & 2) == 0): utilities.print_new_cycle(self.cycle_num)

            # clock changes
            self.RegPC.clock()
            self.RF.clock()

            # read PC
            self.signals.PC = self.RegPC.read()
            self.signals.PC_4 = self.signals.PC_new = self.signals.PC + 4
            if ((self.mode & 2) == 0): utilities.println_int("PC", self.signals.PC)
            if (self.signals.PC > ending_PC): 
                if ((self.mode & 2) == 0): print("No More Instructions")
                i_cycles -= 1 
                break

            self.I_Mem.set_address(self.signals.PC)
            self.I_Mem.run()
            self.signals.instruction = self.I_Mem.get_data() 

            if ((self.mode & 2) == 0): utilities.println_int("instruction", self.signals.instruction)

            # Now you have PC and the instruction
            # Some signals' value can be extracted from instruction directly 
            self.signals_from_instruction(self.signals.instruction, self.signals)

            # call main_control
            self.main_control(self.signals.opcode, self.signals)
            
            # call sign_extend
            self.signals.Sign_extended_immediate = self.sign_extend(self.signals.immediate)
            
            # Write_register. Also an example of using MUX
            self.signals.Write_register = MUX_2_1(self.signals.rt, self.signals.rd, self.signals.RegDst) 
            
            # ALU control
            self.signals.ALU_operation = self.ALU_control(self.signals.ALUOp, self.signals.funct)
            
            # Calculate branch address 
            self.signals.Branch_address = self.calculate_branch_address(self.signals.PC_4, self.signals.Sign_extended_immediate)
            self.signals.Jump_address = self.calculate_jump_address(self.signals.PC_4, self.signals.instruction)
            
            # Print out signals generated in Phase 1.
            if ((self.mode & 4) == 0): utilities.print_signals_1(self.signals)

            # If phase 1 only, continue to the next instruction.
            if ((self.mode & 1) != 0):
                self.RegPC.set_data(self.signals.PC_4)
                self.RegPC.set_write(1)
                continue
            
            # You will continue to complete the core in phase 2
            # Use RF, ALU, D_Mem 
            # Preapre RF write 
            # Compute PC_new 

            # RF Inputs
            self.RF.set_read_registers(self.signals.rs, self.signals.rt)
            self.signals.Write_register = MUX_2_1(self.signals.rt, self.signals.rd, self.signals.RegDst)
            self.RF.set_write_register(self.signals.Write_register)
            self.RF.set_regwrite(self.signals.RegWrite)

            # RF Outputs
            self.signals.RF_read_data_1 = self.RF.get_read_data_1()
            self.signals.RF_read_data_2 = self.RF.get_read_data_2()

            # ALU Input
            self.signals.ALU_input_2 = MUX_2_1(self.signals.RF_read_data_2, self.signals.Sign_extended_immediate, self.signals.ALUSrc)
            
            # ALU Output
            self.signals.ALU_returned_value = ALU_32(self.signals.RF_read_data_1, self.signals.ALU_input_2, self.signals.ALU_operation)
            self.signals.ALU_result = self.signals.ALU_returned_value[0]
            self.signals.ALU_Zero = self.signals.ALU_returned_value[1]

            # D-Mem Input
            self.D_Mem.set_address(self.signals.ALU_result)
            self.D_Mem.set_data(self.signals.RF_read_data_2)
            self.D_Mem.set_memread(self.signals.MemRead)
            self.D_Mem.set_memwrite(self.signals.MemWrite)
        
            # D-Mem Output
            self.D_Mem.run()
            self.signals.Mem_read_data = self.D_Mem.get_data()

            #I_Mem Write Data
            self.signals.Write_data = MUX_2_1(self.signals.ALU_result, self.signals.Mem_read_data, self.signals.MemtoReg)
            self.RF.set_write_data(self.signals.Write_data)

            # Determine new PC 
            self.signals.PCSrc = AND_2(self.signals.Branch , self.signals.ALU_Zero)
            self.signals.PC_branch = MUX_2_1(self.signals.PC_4, self.signals.Branch_address,  self.signals.PCSrc)
            self.signals.PC_new = MUX_2_1(self.signals.PC_branch, self.signals.Jump_address, self.signals.Jump)

            self.RegPC.set_data(self.signals.PC_new)
            self.RegPC.set_write(1)

            # Print out signals generated in Phase 2.
            if ((self.mode & 8) == 0): utilities.print_signals_2(self.signals)
        return i_cycles
            
    
    def signals_from_instruction (self, instruction, sig):
        """
        Extract the following signals from instruction.
            opcode, rs, rt, rd, funct, immediate
        """

        sig.opcode = (instruction >> 26) & 0x3F
        sig.rs = (instruction >> 21) & 0x1F
        sig.rt = (instruction >> 16) & 0x1F
        sig.rd = (instruction >> 11) & 0x1F
        sig.funct = instruction & 0x3F
        sig.immediate = instruction & 0xFFFF

    def main_control(self, opcode, sig):
        """
        Check the type of input instruction
        """
        #set defaults for control signals 
        sig.RegDst = sig.Jump = sig.Branch = sig.MemRead = sig.MemtoReg = sig.ALUOp = sig.MemWrite = sig.ALUSrc = sig.RegWrite = 0

        #determine control signals
        if opcode == 0:             # R-Type 000000
            sig.RegWrite = 1
            sig.RegDst = 1
            sig.ALUOp = 2           # 10

        elif opcode == 8:           # I-type addi
            sig.RegWrite = 1
            sig.ALUSrc   = 1 

        elif opcode == 35:          # I-type lw
            sig.RegWrite = 1
            sig.MemRead  = 1
            sig.MemtoReg = 1
            sig.ALUSrc   = 1

        elif opcode == 43:          # I-type sw
            sig.MemWrite = 1    
            sig.ALUSrc   = 1

        elif opcode == 4:           # I-type beq
             sig.Branch = 1
             sig.ALUOp  = 1         # 01

        elif opcode == 2:           # J-type j
            sig.Jump = 1

        else:
            raise ValueError("Unknown opcode 0x%02X" % opcode)
        return

    def ALU_control(self, alu_op, funct):  
        """
        Get alu_control from func field of instruction
        Input: function field of instruction
        Output: alu_control_out
       
        """
        alu_control_out = 0
        # One example is given, continue to finish other cases.
        if alu_op == 0:             # 00  
            alu_control_out = 2     # 0010
        
        elif alu_op == 1:           # 01
            alu_control_out = 6     # 0110

        elif alu_op == 2:               # 10
            if funct == 32:             # add-100000
                alu_control_out = 2     # 0010
            elif funct == 34:           # sub-100010
                alu_control_out = 6     # 0110
            elif funct == 36:           # and 100100
                alu_control_out = 0     # 0000
            elif funct == 37:           # or-100101
                alu_control_out = 1     # 0110
            elif funct == 38:           # slt-100110
                alu_control_out = 7     # 0111
            else:
                raise ValueError("Unknown opcode code 0x%02X" % alu_op)            

        else:
           raise ValueError("Unknown opcode code 0x%02X" % alu_op)
        return alu_control_out

    def sign_extend(self, immd):
        """
        Sign extend module. 
        Convert 16-bit to an int.
        Extract the lower 16 bits. 
        If bit 15 of immd is 1, compute the correct negative value (immd - 0x10000).
        """
        if (immd >> 15) == 0:                       # check first bit
            immd = immd & 0xFFFF                    # extend 0's
        else:
            immd = (immd - 0x10000)    # extend 1's
        return immd

    def calculate_branch_address(self, pc_4, extended):
        addr = (extended << 2) + pc_4     # calculate pc for branch        
        return addr

    def calculate_jump_address(self, pc_4, instruction):
        addr = ((instruction & 0x3FFFFFF) << 2) | (pc_4 & 0xF0000000)   # calculate pc for jump
        return addr

