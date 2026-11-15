# Introduction to java programming

## Introduction

In this lesson, you will learn to:

- Explain what Java is and why it is used in the world.
- Identify the main parts of a simple Java program.
- Describe the role of the main method in a Java program.
- Apply the basic syntax to write a program that prints text.
- Explain what a variable is and how to use it to store a number.
- List the steps to run a Java program on a computer.
- Describe what to learn next to continue the Java journey.

## What is Java and Why It Matters

A **Programming Language** is a set of rules that people use to give instructions to a computer. Java is a computer language used to build software.

**Software** is a program that runs on a computer or phone to do a specific job. Java is popular because it runs on many different devices.

You can use Java to build websites, mobile apps, and business software.

Think of Java like a recipe book. The book gives you clear steps to cook a meal that works on any kitchen.

Here is how this works in real life:
1. You write a recipe in a book. This is like writing code in Java.
2. You follow the steps in the book to cook a meal. This is like the computer running the Java code.
3. The meal tastes the same no matter which kitchen you use. This is like the software working on any device.

This example shows that Java provides clear steps to create software that works everywhere.

## The Main Parts of a Java Program

In the last section, you learned that Java is a set of rules to give instructions to a computer. Now, you will see how those rules are put together to make a working program.

A Java program is made of blocks of code. Think of a program as a big box. Inside this box, we put smaller boxes. Each of these smaller boxes holds a specific set of instructions. These smaller boxes are called blocks of code. They help us organize the work the computer needs to do.

The first block is the class definition. A **class** is a container that holds all the information and instructions for a specific thing. It is like a blueprint for a house. The blueprint tells the builder what materials to use and how to put them together. In Java, the class definition is the first block you write. It sets the stage for the rest of the program.

The second block is the main method, which is the starting point. A **method** is a block of code that does a specific task. You can think of a method as a small tool in a toolbox. The main method is the most important tool. It is the first thing the computer runs when you start the program. It is the main door you enter to start the program.

Here is a simple example to show how these parts work together. Imagine you want to make a program that says "Hello" to the world.

1. You start by creating a class. You give it a name, like "MyProgram". This is the container.
2. Inside this container, you write the main method. You give it the special name "main".
3. You put a message inside the main method. The message is "Hello World".
4. When you run the program, the computer looks for the main method.
5. It enters the main method and shows the message "Hello World".

This example shows how a class holds the code and the main method is the starting point.

## Writing Your First Java Program

You will now write a simple program to print a message on the screen. This builds on the idea of a class as a container for instructions.

A program must have a class name that matches the file name. In Java, the name of the class is very important. If you name the class "Hello", you must save the file as "Hello.java". If the names do not match, the computer will not run the program.

The main method must be public and static. The main method is the starting point of the program. The word "public" means anyone can run it. The word "static" means it belongs to the class, not to a specific object. The computer looks for this specific line to begin the work.

The program prints text to the screen using System.out.println. This line sends text to the user. It is like writing a note on a board for everyone to see. The word "println" means print a line and then move to the next line.

A **public static void main** is a special line of code that tells the computer where to start. A **System.out.println** is a command that shows text on the screen.

Here is how you write the program step by step:
1. Open a text editor like Notepad.
2. Type the class name: public class Hello.
3. Type the main method: public static void main(String[] args).
4. Type the print command: System.out.println("Hello World").
5. Save the file as "Hello.java" in a folder.

This example shows the three main rules for a working Java program.

## Running a Java Program

You need a Java Development Kit (JDK) to run Java. The JDK is a set of tools that helps you write and run Java programs. It is like a box of special pens and paper for writing code. Without this kit, the computer cannot understand or run your program.

You write the code in a text file with a .java extension. You must save your work with the name of your class and the letters ".java" at the end. This tells the computer that the file contains Java code. If you forget the ".java" part, the computer will not recognize it as a program.

You use a command to compile and run the program. The first command turns your text into a form the computer can read. The second command actually starts the program and shows the result. These commands are typed in a special window called a terminal.

A **compile** is the process of turning your text code into a form the computer can read. You use a command to do this. The second command runs the program and shows the result on the screen.

Writing the code is like writing a letter, and running it is like mailing the letter to be read. You first write the letter on paper. Then you put it in an envelope and mail it to a friend. The friend reads the letter and understands your message.

Here is how you do this with a simple program:
1. You write the code in a file named "Hello.java".
2. You open a terminal window on your computer.
3. You type the command "javac Hello.java" to compile the code.
4. The computer creates a new file named "Hello.class".
5. You type the command "java Hello" to run the program.
6. The message "Hello World" appears on the screen.

This example shows the process of writing code and then running it to see the result.

## Storing Data with Variables

In the last section, you learned how to print text on the screen. Now, you will learn how to keep data in your program. This helps you work with numbers and words.

A **variable** is a named box to store a value. Think of a box as a container. You can put a number or a word inside this box. You can also take the value out later. The name of the box helps you find it easily.

You must declare a variable with a type and a name. The **data type** tells the computer what kind of data is inside. The name is the label you put on the box. You must write both the type and the name when you create the box. This tells the computer how much space to save for the data.

You can change the value inside the variable later. The box is not fixed. You can take the old value out and put a new one in. This is useful if the data changes over time. You can update the value as many times as you need.

Imagine you have a box for your age. You can put your age in the box. Later, you can change the number in the box to your new age. This shows how variables work in a program.

1. You create a box for a number. You call it "age".
2. You put the number 20 inside the box.
3. You print the number from the box. The screen shows 20.
4. You change the number in the box to 21.
5. You print the number from the box again. The screen shows 21.

This example shows how to create a variable, put a value in it, and change that value later.

## A Real-World Example: A Simple Calculator

Java can be used to perform calculations. This means the computer can do math for you. You can use it to add, subtract, multiply, or divide numbers. This is very useful for many tasks in daily life.

You can store numbers in variables and add them. A variable is a box that holds a value. You can put a number into the box. Then, you can take the number out and add it to another number. This helps you keep track of the data you are working with.

The result can be printed to the screen. After you do the math, you want to see the answer. You can use a command to show the answer on the monitor. This lets you check if your calculation is correct.

An **Integer** is a whole number. It does not have a decimal point. For example, 5 and 10 are integers. 5.5 is not an integer because it has a decimal.

**Addition** is the process of joining two numbers together. It is the act of adding one number to another. The symbol for addition is the plus sign (+).

Here is a simple example of a calculator app. Imagine you want to add the price of a book and a pen. The book costs 50 rupees. The pen costs 20 rupees. You want to know the total cost.

1. You create a box named `bookPrice` and put the number 50 inside it.
2. You create another box named `penPrice` and put the number 20 inside it.
3. You create a third box named `totalCost` to hold the result.
4. You add the number in `bookPrice` to the number in `penPrice`.
5. You put the new total, 70, into the `totalCost` box.
6. You print the number 70 on the screen.

This example shows how to use variables to store numbers and add them to find a total.

## Summary and What to Learn Next

In this section, we will review what you have learned about Java. We will also look at the next step in your learning path.

Java is a popular language for building software. Many companies use it to create apps and websites. It is a strong tool for your career.

A program has a class and a main method. The class is the main container for your code. The main method is the starting point where the program begins to run.

Variables are used to store data. You can think of a variable as a box. You put a value inside the box to keep it safe. You can use this value later in your program.

The next step is to learn about data types and math operations. You need to know what kind of data you can store. You also need to know how to do math with those numbers.

Here is a quick recap of what we did in the calculator example. We created a class to hold our code. We used a main method to start the program. We created variables to hold numbers. We added the numbers together. We printed the result to the screen.

This example shows the basic structure of a Java program and how to run it.
