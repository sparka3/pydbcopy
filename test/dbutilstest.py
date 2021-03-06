import unittest
import datetime
from dbutils import MySQLHost
from config import settings 
import os
import multiprocessing
import logging
import sys


logger = multiprocessing.get_logger()
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(processName)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)

class MySQLHostTest(unittest.TestCase):
    """
        These tests need a world writable dump dir. The default directory is /share/mysql_dumps.
        Please keep in mind that issuing the SQL 'select into outfile' will cause mysql to write
        files as the user mysql is running as. The dump dir needs to be world writable so that 
        these tests can clean up the temp files that the mysql user writes. 
    """
    
    def setUp(self):
        settings.read_properties("pydbcopy.conf")

        self.source_host = MySQLHost(settings.source_host, settings.source_user, \
                                     settings.source_password, settings.source_database)
        self.dest_host = MySQLHost(settings.target_host, settings.target_user, \
                                   settings.target_password, settings.target_database)
    
        #
        # Just in case lets tear down an old or canceled run...
        #
        self.tearDown()
        
        #
        # Bring up the fixture
        #
        c = self.source_host.conn.cursor()
        c.execute("SET AUTOCOMMIT=1")
        c.execute("create table if not exists tmp_pydbcopy_test ( id integer primary key, test_string varchar(50) )")
        c.execute("insert into tmp_pydbcopy_test (id,test_string) values (1,'test')")
        c.execute("create table if not exists tmp_hashed_pydbcopy_test ( id integer primary key, test_string varchar(50), fieldHash varchar(50) )")
        c.execute("insert into tmp_hashed_pydbcopy_test (id,test_string,fieldHash) values (1,'test','123')")
        c.execute("insert into tmp_hashed_pydbcopy_test (id,test_string,fieldHash) values (2,'test1','234')")
        c.execute("insert into tmp_hashed_pydbcopy_test (id,test_string,fieldHash) values (3,'test2','345')")
        c.execute("create table if not exists tmp_pydbcopy_modified_test ( id integer primary key, test_string varchar(50), lastModifiedDate timestamp NOT NULL default CURRENT_TIMESTAMP on update CURRENT_TIMESTAMP )")
        c.execute("insert into tmp_pydbcopy_modified_test (id,test_string,lastModifiedDate) values (1,'test','2010-11-23 05:00:00')")
        c.close()

    def tearDown(self):
        #
        # Tear down the fixture
        #
        c = self.source_host.conn.cursor()
        c.execute("SET AUTOCOMMIT=1")
        c.execute("drop table if exists tmp_pydbcopy_test")
        c.execute("drop table if exists tmp_hashed_pydbcopy_test")
        c.execute("drop table if exists tmp_pydbcopy_modified_test")
        
        c = self.dest_host.conn.cursor()
        c.execute("SET AUTOCOMMIT=1")
        c.execute("drop table if exists tmp_pydbcopy_test")
        c.execute("drop table if exists tmp_hashed_pydbcopy_test")
        c.execute("drop table if exists tmp_pydbcopy_modified_test")
        c.close()

    def testTableExists(self):
        self.assertTrue(self.source_host.table_exists("tmp_pydbcopy_test"))
        self.assertFalse(self.source_host.table_exists("tmp_pydbcopy_tests"))
        self.assertFalse(self.source_host.table_exists("pydbcopy_test"))
    
    def testSelectIntoOutfile(self):
        filename = self.source_host.select_into_outfile("tmp_pydbcopy_test", None, settings.dump_dir)
        f = open(filename)
        filecontents = f.read()
        f.close
        os.remove(filename)
        self.assertEquals(filecontents, "1\ttest\n")

    def testLoadDataInFile(self):
        c = self.dest_host.conn.cursor()
        c.execute("SET AUTOCOMMIT=1")
        
        c.execute("create table if not exists tmp_pydbcopy_test ( id integer primary key, test_string varchar(50) )")
        
        filename = "fixtures/testLoadDataInFile.csv"
        
        self.dest_host.load_data_in_file("tmp_pydbcopy_test", filename)

        c.execute("select * from tmp_pydbcopy_test")
        rows = c.fetchone()
        
        self.assertEquals(rows[0], 1)
        self.assertEquals(rows[1], 'test')
        
        c.close()
        
    def testTruncateTable(self):
        c = self.dest_host.conn.cursor()
        c.execute("SET AUTOCOMMIT=1")
        
        c.execute("create table if not exists tmp_hashed_pydbcopy_test ( id integer primary key, test_string varchar(50), fieldHash varchar(50) )")
        c.execute("insert into tmp_hashed_pydbcopy_test (id,test_string,fieldHash) values (1,'test','123')")
        c.execute("insert into tmp_hashed_pydbcopy_test (id,test_string,fieldHash) values (2,'test1','234')")
        c.execute("insert into tmp_hashed_pydbcopy_test (id,test_string,fieldHash) values (3,'test2','345')")
        
        c.execute("select * from tmp_hashed_pydbcopy_test")
        rows = c.fetchall()
        
        self.assertEquals(len(rows), 3)
        
        self.dest_host.truncate_table("tmp_hashed_pydbcopy_test")
        
        c.execute("select * from tmp_hashed_pydbcopy_test")
        rows = c.fetchall()
        
        self.assertEquals(len(rows), 0)
        
        c.close()
        
    def testGetTableStructure(self):
        expected = "CREATE TABLE `tmp_pydbcopy_test` (\n" \
                 + "  `id` int(11) NOT NULL,\n" \
                 + "  `test_string` varchar(50) DEFAULT NULL,\n" \
                 + "  PRIMARY KEY (`id`)\n" \
                 + ") ENGINE=MyISAM DEFAULT CHARSET=utf8"
        self.assertEquals(self.source_host.get_table_structure("tmp_pydbcopy_test"), expected)
    
    def testGetTableMaxLastModified(self):
        failure = -1
        self.assertEquals(self.source_host.get_table_max_modified("RunningJobs"), failure)
        expected = datetime.datetime(2010, 11, 23, 5, 0)
        self.assertEquals(self.source_host.get_table_max_modified("tmp_pydbcopy_modified_test"), expected)

    def testCreateTableWithSchema(self):
        c = self.source_host.conn.cursor()
                
        expected = "CREATE TABLE `tmp_pydbcopy_test` (\n" \
                 + "  `id` int(11) NOT NULL,\n" \
                 + "  `test_string` varchar(50) DEFAULT NULL,\n" \
                 + "  PRIMARY KEY (`id`)\n" \
                 + ") ENGINE=MyISAM DEFAULT CHARSET=utf8"
        
        self.dest_host.create_table_with_schema("tmp_pydbcopy_test", expected)
  
        c.execute("show create table %s" % ("tmp_pydbcopy_test"))
        rows = c.fetchone()
        struct = rows[1]
        
        self.assertEquals(struct, expected)
        
        c.close()
        
    def testGetCurrentHashSet(self):
        expected = set([ "123", "234", "345" ])
        self.assertEquals(self.source_host.get_current_hash_set("tmp_hashed_pydbcopy_test"), expected)

    def testDeleteRecords(self):
        c = self.dest_host.conn.cursor()
        c.execute("SET AUTOCOMMIT=1")
        
        c.execute("create table if not exists tmp_hashed_pydbcopy_test ( id integer primary key, test_string varchar(50), fieldHash varchar(50) )")
        c.execute("insert into tmp_hashed_pydbcopy_test (id,test_string,fieldHash) values (1,'test','123')")
        c.execute("insert into tmp_hashed_pydbcopy_test (id,test_string,fieldHash) values (2,'test1','234')")
        c.execute("insert into tmp_hashed_pydbcopy_test (id,test_string,fieldHash) values (3,'test2','345')")
        
        self.dest_host.delete_records("tmp_hashed_pydbcopy_test", set([ "123", "345" ]))
        
        c.execute("select * from tmp_hashed_pydbcopy_test")
        rows = c.fetchall()
        
        self.assertEquals(rows[0][0], 2)
        self.assertEquals(rows[0][1], 'test1')
        self.assertEquals(rows[0][2], '234')
        
        c.close()
        
    def testDeleteRecordsBatching(self):
        c = self.dest_host.conn.cursor()
        c.execute("SET AUTOCOMMIT=1")
        
        c.execute("create table if not exists tmp_hashed_pydbcopy_test ( id integer primary key, test_string varchar(50), fieldHash varchar(50) )")
        
        cur_record = 0
        delete_set = set([])
        while cur_record <= 25000:
            c.execute("insert into tmp_hashed_pydbcopy_test (id,test_string,fieldHash) values (%s,'%s','%s')" % (cur_record, cur_record, cur_record))
            if cur_record > 0 and cur_record < 21000:
                delete_set.add("%s" % cur_record)
            cur_record = cur_record + 1 
        
        
        self.dest_host.delete_records("tmp_hashed_pydbcopy_test", delete_set)
        
        c.execute("select * from tmp_hashed_pydbcopy_test order by id")
        rows = c.fetchall()
        
        self.assertEquals(len(rows), 4002)
        
        self.assertEquals(rows[0][0], 0)
        self.assertEquals(rows[1][0], 21000)
        self.assertEquals(rows[2][0], 21001)
        self.assertEquals(rows[4001][0], 25000)
        
        c.close()
        
    def testGetRowCount(self):
        self.assertEquals(self.source_host.get_row_count("tmp_hashed_pydbcopy_test"), 3)

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
