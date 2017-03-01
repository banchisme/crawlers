#author: Shi Pu
#date: Feb 23, 2016

#import libraries
import requests
import pandas as pd
from lxml import html
from tqdm import tqdm
import re

#define output files
output_file='cc_course_catlog.xls'

#define website layout
campus_url='http://catalog.tncc.edu/'
course_catlog_url='http://catalog.tncc.edu/content.php?catoid=1&navoid=36'
sem_nodeXpath='//div[@class="acalog-core"]/h2[contains(text(),"Fall") or contains(text(),"Spring")]/..'
footnotesXpath='//div[@class="acalog-core"]/h2[contains(text(),"Total Minimum Credits")]/../p'

#default programs
programs=['Business Administration (213)','Engineering (831)','Science (880)']

#************************
#lvl one/top functions
#************************

def derive_programs_links(programs,course_catlog):
    #input:  programs names, and the course_catlog html file
    #output: programs links
    program_links={}

    for p in programs:
        myXpath='//*[contains(text(), "PROGRAM")]/@href'.replace('PROGRAM',p)
        program_links[p]=campus_url+course_catlog.xpath(myXpath)[0]

    return program_links

def derive_programs_courses(program_links,semXpath=sem_nodeXpath,ftXpath=footnotesXpath):
    #input:   programs links
    #output:  programs courses
    df=pd.DataFrame()

    for program,prog_link in tqdm(program_links.iteritems()):
        prog_df=derive_program_courses(prog_link) #draw course_information from a single course
        prog_df['program']=program
        df=df.append(prog_df)

    #re-organize the df
    sem_order={'Fall I': 1,'Spring I':2, 'Fall II': 3, 'Spring II': 4}
    df['semester order']=df['suggest semester'].apply(lambda sem: sem_order[sem])
    df.sort_values(['program','semester order'],inplace=True)
    df=df[['program','suggest semester','course code','course name','course credits','suggested courses']]
    df.index=range(df.shape[0])

    return df

def derive_program_courses(program_link,semXpath=sem_nodeXpath,ftXpath=footnotesXpath):
    # input:  a single program's linke
    # output: courses for a single program
    # assume the webpage layout is not changed, modify if the webpage is updated
    progam_node=html.fromstring(requests.get(program_link).text)

    semester_nodes=progam_node.xpath(semXpath)
    footnotes=progam_node.xpath(ftXpath)

    ft_dict=parse_footnotes(footnotes)
    prog_dict=parse_semester_nodes(semester_nodes)

    df=pack_as_df(prog_dict)

    df['suggested courses']=df['sup'].apply(lambda x: link_sup_footnote(x,ft_dict))

    return df

#************************
#lvl two/bottom functions
#************************
def link_sup_footnote(sup,ft_dict):
    #input:  supperscript and the footnote dictionary where the supperscript is the key, and the footnote content
    #        is the value
    #output: the content of footnote corresponding to the input supperscript

    if sup=='':
        return ''
    else:
        sup_list=sup.split(',')
        suggest_courses_raw=[find_suggest_courses(ft_dict[s]) for s in sup_list]
        suggest_courses_raw=filter(lambda x: x<>'',suggest_courses_raw) #filter empty strings: ''
        return ','.join(set(suggest_courses_raw))

def parse_footnotes(footnodes):
    #input:  footnote nodes, a list of html nodes
    #output: footnote dictionary, key is the supperscript, value is the footnote content

    #assume that every footnote is seperated by '.'
    #no useful information in unicode characters
    #split into lists based on '.'

    ft_dict={}

    for footnode in footnodes:
        ft=footnode.text_content() #extract text from the footnote node
        raw=ft.encode('ascii','ignore').split('.')
        raw=[f.strip() for f in raw] #strip \n and \s
        raw=filter(lambda x: x<>'',raw) #clean empty string

        for f in raw:
            if re.search('^[0-9]+',f):
                key=re.findall('^[0-9]+',f)[0]
                val=re.findall('^[0-9]+(.+)',f)[0]
                ft_dict[key]=val

    return ft_dict

def find_suggest_courses(ft,pt='[A-Z][A-Z][A-Z]\s*[0-9][0-9][0-9]'):
    #inputs: footnote content, course code pattern
    #outputs: course codes in the footnote content, seperated by ','
    #assumption: the course code pattern is three letters,space, and three digits

    return ','.join(set(re.findall(pt,ft)))


def combine_selective(l,kwd='or'):
    # input is a list of items: [x1,x2,'or',x3,x4]
    # output is a list of combined items: [x1,[x2,x3],x4]
    # assuming the list is not null
    # assuming the list does not end with keyword

    result=[]

    if len(l)==1:
        result=l
    else:
        pt=1
        currentItem=[l[pt-1]]

        while pt<>len(l):
            if l[pt]=='or':
                currentItem.append(l[pt+1])
                pt+=2
            else:
                result.append(currentItem)
                currentItem=[l[pt]]
                pt+=1

        result.append(currentItem)
    return result

def parse_semester_nodes(semester_nodes):
    #inputs:     a list of semester nodes, in html nodes
    #outputs:    a program dictionary, the key is a semester, the value is a list of courses should be taken in the semester
    #assumption: web layout for semester, and course; see the xpath inside
    prog_dict={}

    for semester_node in semester_nodes:
        semester=semester_node.xpath('./h2/text()')[0] #find semester

        course_nodes=semester_node.xpath('./ul/li')
        raw=[n.text_content().encode('ascii','ignore') for n in course_nodes] #clean non-ascii codes
        raw=filter(lambda x: x<>'',raw) #remove empty strings
        raw=combine_selective(raw) #combine selectives
        prog_dict[semester]=raw

    return prog_dict

def parse_course(raw):
    #inputs:      a string contains: 1. course code; 2. course name; 3. course credits; 4. supperscripts
    #outputs:     a dictionary contains the 4 information listed above
    #assumptions: 1. course code is always  '[A-Z][A-Z][A-Z]\s*[0-9][0-9][0-9]' or missing
    #             2. the credits always has the key word 'credit'
    #             3. course name is between the '-' after course code, and the '(' before credits

    if re.findall('(.+)-',raw)<>[]:
        code_val=re.findall('[A-Z][A-Z][A-Z]\s*[0-9][0-9][0-9]',raw)[0].strip()
        crse_val=re.findall('-(.+)\\(',raw)[0].strip()
    else:
        code_val=''
        crse_val=re.findall('(.+)\\(',raw)[0].strip()

    cred_val=re.findall('[0-9]+\scredit',raw)[0].strip()

    if re.findall('credits?\)(.+)',raw)<>[]:
        sup_val=re.findall('credits?\)(.+)',raw)[0].strip()
    else:
        sup_val=''

    return {'course code':code_val,'course name': crse_val, 'course credits': cred_val, 'sup': sup_val}

def parse_course_list(courses):
    #inputs:        a list of course strings;
    #               it is either a single course, or multiple electives

    #outputs:       a course dictionary; for electives, they share the same key, and val are seperated by '/'
    #assumptions:   NA

    parsed_courses=[]

    for course in courses:
        parsed_courses.append(parse_course(course))

    if len(parsed_courses)==1: #if not a selective
        return parsed_courses[0]
    else:
        #merge the two courses into one record
        new_dict={}
        for key in parsed_courses[0]:
            new_dict[key]='/'.join(filter(lambda x: x<>'',[pc[key] for pc in parsed_courses]))
        return new_dict

def pack_as_df(prog_dict):
    #inputs:       a program dictionary: the key is a semester, the values are a list of course lists.
    #outputs:      a df witht columns: course code, course name, course credits, sup, suggested semester
    #assumptions:  NA

    df=pd.DataFrame()

    for key,values in prog_dict.iteritems():
        for value in values:
            try:
                row=parse_course_list(value)
                row['suggest semester']=key
                df=df.append(pd.DataFrame(row,index=[0]))
            except:
                print "error!"
                print key
                print values
    return df

def main():
    #download the course_catlog information from web
    course_catlog=html.fromstring(requests.get(course_catlog_url).text)

    #find the corresponding links for the interested programs
    programs_links=derive_programs_links(programs,course_catlog)

    #generate a df based on the program links
    df=derive_programs_courses(programs_links)

    #store df as a excel file
    df.to_excel(output_file,index=False)
    print 'work is done!'

if __name__ == "__main__":
    main()
