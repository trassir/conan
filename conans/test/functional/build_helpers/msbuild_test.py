import os
import platform
import textwrap
import unittest

import pytest
import six
from nose.plugins.attrib import attr
from parameterized import parameterized

from conans.client.tools.files import replace_in_file
from conans.model.ref import PackageReference
from conans.paths import CONANFILE
from conans.test.utils.deprecation import catch_deprecation_warning
from conans.test.utils.tools import TestClient
from conans.test.utils.visual_project_files import get_vs_project_files
from conans.util.files import load


class MSBuildTest(unittest.TestCase):

    @attr('slow')
    @pytest.mark.slow
    @unittest.skipUnless(platform.system() == "Windows" and six.PY3, "Requires MSBuild")
    def test_build_vs_project(self):
        conan_build_vs = """
from conans import ConanFile, MSBuild

class HelloConan(ConanFile):
    name = "Hello"
    version = "1.2.1"
    exports = "*"
    settings = "os", "build_type", "arch", "compiler", "cppstd"

    def build(self):
        msbuild = MSBuild(self)
        msbuild.build("MyProject.sln", verbosity="normal")

    def package(self):
        self.copy(pattern="*.exe")
"""
        client = TestClient()

        # Test cpp standard stuff

        files = get_vs_project_files(std="cpp17_2015")
        files[CONANFILE] = conan_build_vs

        client.save(files)
        with catch_deprecation_warning(self):
            client.run('create . Hello/1.2.1@lasote/stable -s cppstd=11 -s '
                       'compiler="Visual Studio" -s compiler.version=14', assert_error=True)
        with catch_deprecation_warning(self, n=2):
            client.run('create . Hello/1.2.1@lasote/stable -s cppstd=17 '
                       '-s compiler="Visual Studio" -s compiler.version=14')
        self.assertIn("Packaged 1 '.exe' file: MyProject.exe", client.out)

        files = get_vs_project_files()
        files[CONANFILE] = conan_build_vs

        # Try to not update the project
        client.cache._config = None  # Invalidate cached config

        replace_in_file(client.cache.conan_conf_path, "[general]",
                        "[general]\nskip_vs_projects_upgrade = True", output=client.out)
        client.save(files, clean_first=True)
        client.run("create . Hello/1.2.1@lasote/stable --build")
        self.assertNotIn("devenv", client.out)
        self.assertIn("Skipped sln project upgrade", client.out)

        # Try with x86_64
        client.save(files)
        client.run("export . lasote/stable")
        client.run("install Hello/1.2.1@lasote/stable --build -s arch=x86_64")
        self.assertIn("Release|x64", client.out)
        self.assertIn("Packaged 1 '.exe' file: MyProject.exe", client.out)

        # Try with x86
        client.save(files, clean_first=True)
        client.run("export . lasote/stable")
        client.run("install Hello/1.2.1@lasote/stable --build -s arch=x86")
        self.assertIn("Release|x86", client.out)
        self.assertIn("Packaged 1 '.exe' file: MyProject.exe", client.out)

        # Try with x86 debug
        client.save(files, clean_first=True)
        client.run("export . lasote/stable")
        client.run("install Hello/1.2.1@lasote/stable --build -s arch=x86 -s build_type=Debug")
        self.assertIn("Debug|x86", client.out)
        self.assertIn("Packaged 1 '.exe' file: MyProject.exe", client.out)

        # Try with a custom property file name
        files[CONANFILE] = conan_build_vs.replace(
                'msbuild.build("MyProject.sln", verbosity="normal")',
                'msbuild.build("MyProject.sln", verbosity="normal", property_file_name="mp.props")')
        client.save(files, clean_first=True)
        client.run("create . Hello/1.2.1@lasote/stable --build -s arch=x86 -s build_type=Debug")
        self.assertIn("Debug|x86", client.out)
        self.assertIn("Packaged 1 '.exe' file: MyProject.exe", client.out)
        full_ref = "Hello/1.2.1@lasote/stable:b786e9ece960c3a76378ca4d5b0d0e922f4cedc1"
        pref = PackageReference.loads(full_ref)
        build_folder = client.cache.package_layout(pref.ref).build(pref)
        self.assertTrue(os.path.exists(os.path.join(build_folder, "mp.props")))

    @attr('slow')
    @pytest.mark.slow
    @unittest.skipUnless(platform.system() == "Windows", "Requires MSBuild")
    def test_user_properties_file(self):
        conan_build_vs = textwrap.dedent("""
            from conans import ConanFile, MSBuild

            class HelloConan(ConanFile):
                exports = "*"
                settings = "os", "build_type", "arch", "compiler"

                def build(self):
                    msbuild = MSBuild(self)
                    msbuild.build("MyProject.sln", verbosity="normal",
                                  definitions={"MyCustomDef": "MyCustomValue"},
                                  user_property_file_name="myuser.props")

                def package(self):
                    self.copy(pattern="*.exe")
            """)
        client = TestClient()

        files = get_vs_project_files()
        files[CONANFILE] = conan_build_vs
        props = textwrap.dedent("""<?xml version="1.0" encoding="utf-8"?>
            <Project ToolsVersion="4.0" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
              <ImportGroup Label="PropertySheets" />
              <PropertyGroup Label="UserMacros" />
              <ItemDefinitionGroup>
                <ClCompile>
                  <RuntimeLibrary>MultiThreaded</RuntimeLibrary>
                </ClCompile>
              </ItemDefinitionGroup>
              <ItemGroup />
            </Project>
            """)
        files["myuser.props"] = props

        client.save(files)
        client.run('create . Hello/1.2.1@lasote/stable')
        self.assertNotIn("/EHsc /MD", client.out)
        self.assertIn("/EHsc /MT", client.out)
        self.assertIn("/D MyCustomDef=MyCustomValue", client.out)
        self.assertIn("Packaged 1 '.exe' file: MyProject.exe", client.out)

        full_ref = "Hello/1.2.1@lasote/stable:6cc50b139b9c3d27b3e9042d5f5372d327b3a9f7"
        pref = PackageReference.loads(full_ref)
        build_folder = client.cache.package_layout(pref.ref).build(pref)
        self.assertTrue(os.path.exists(os.path.join(build_folder, "myuser.props")))
        conan_props = os.path.join(build_folder, "conan_build.props")
        content = load(conan_props)
        self.assertIn("<RuntimeLibrary>MultiThreadedDLL</RuntimeLibrary>", content)

    @attr('slow')
    @pytest.mark.slow
    @unittest.skipUnless(platform.system() == "Windows", "Requires MSBuild")
    def test_user_properties_multifile(self):
        conan_build_vs = textwrap.dedent("""
            from conans import ConanFile, MSBuild

            class HelloConan(ConanFile):
                exports = "*"
                settings = "os", "build_type", "arch", "compiler"

                def build(self):
                    msbuild = MSBuild(self)
                    msbuild.build("MyProject.sln", verbosity="normal",
                                  definitions={"MyCustomDef": "MyCustomValue"},
                                  user_property_file_name=["myuser.props", "myuser2.props"])

                def package(self):
                    self.copy(pattern="*.exe")
            """)
        client = TestClient()

        files = get_vs_project_files()
        files[CONANFILE] = conan_build_vs
        props = textwrap.dedent("""<?xml version="1.0" encoding="utf-8"?>
            <Project ToolsVersion="4.0" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
              <ImportGroup Label="PropertySheets" />
              <PropertyGroup Label="UserMacros" />
              <ItemDefinitionGroup>
                <ClCompile>
                    <PreprocessorDefinitions>MyCustomDef2=MyValue2;%(PreprocessorDefinitions)
                    </PreprocessorDefinitions>
                </ClCompile>
              </ItemDefinitionGroup>
              <ItemGroup />
            </Project>
            """)
        props2 = textwrap.dedent("""<?xml version="1.0" encoding="utf-8"?>
            <Project ToolsVersion="4.0" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
              <ImportGroup Label="PropertySheets" />
              <PropertyGroup Label="UserMacros" />
              <ItemDefinitionGroup>
                <ClCompile>
                  <RuntimeLibrary>MultiThreaded</RuntimeLibrary>
                </ClCompile>
              </ItemDefinitionGroup>
              <ItemGroup />
            </Project>
            """)
        files["myuser.props"] = props
        files["myuser2.props"] = props2

        client.save(files)
        client.run('create . Hello/1.2.1@lasote/stable')
        self.assertNotIn("/EHsc /MD", client.out)
        self.assertIn("/EHsc /MT", client.out)
        self.assertIn("/D MyCustomDef=MyCustomValue", client.out)
        self.assertIn("/D MyCustomDef2=MyValue2", client.out)
        self.assertIn("Packaged 1 '.exe' file: MyProject.exe", client.out)

        full_ref = "Hello/1.2.1@lasote/stable:6cc50b139b9c3d27b3e9042d5f5372d327b3a9f7"
        pref = PackageReference.loads(full_ref)
        build_folder = client.cache.package_layout(pref.ref).build(pref)
        self.assertTrue(os.path.exists(os.path.join(build_folder, "myuser.props")))
        conan_props = os.path.join(build_folder, "conan_build.props")
        content = load(conan_props)
        self.assertIn("<RuntimeLibrary>MultiThreadedDLL</RuntimeLibrary>", content)

    @unittest.skipUnless(platform.system() == "Windows", "Requires MSBuild")
    def test_reuse_msbuild_object(self):
        # https://github.com/conan-io/conan/issues/2865
        conan_build_vs = """
from conans import ConanFile, MSBuild

class HelloConan(ConanFile):
    name = "Hello"
    version = "1.2.1"
    exports = "*"
    settings = "os", "build_type", "arch", "compiler", "cppstd"

    def configure(self):
        del self.settings.compiler.runtime
        del self.settings.build_type

    def build(self):
        msbuild = MSBuild(self)
        msbuild.build("MyProject.sln", build_type="Release")
        msbuild.build("MyProject.sln", build_type="Debug")
        self.output.info("build() completed")
"""
        client = TestClient()
        files = get_vs_project_files()
        files[CONANFILE] = conan_build_vs

        client.save(files)
        client.run("create . danimtb/testing")
        self.assertIn("build() completed", client.out)

    @parameterized.expand([("True",), ("'my_log.binlog'",)])
    @unittest.skipUnless(platform.system() == "Windows", "Requires MSBuild")
    def test_binary_log_build(self, value):
        conan_build_vs = """
from conans import ConanFile, MSBuild

class HelloConan(ConanFile):
    name = "Hello"
    version = "1.2.1"
    exports = "*"
    settings = "os", "build_type", "arch", "compiler"

    def build(self):
        msbuild = MSBuild(self)
        msbuild.build("MyProject.sln", output_binary_log=%s)
"""
        client = TestClient()
        files = get_vs_project_files()
        files[CONANFILE] = conan_build_vs % value
        client.save(files)
        client.run("install . -s compiler=\"Visual Studio\" -s compiler.version=15")
        client.run("build .")

        if value == "'my_log.binlog'":
            log_name = value[1:1]
            flag = "/bl:%s" % log_name
        else:
            log_name = "msbuild.binlog"
            flag = "/bl"

        self.assertIn(flag, client.out)
        log_path = os.path.join(client.current_folder, log_name)
        self.assertTrue(os.path.exists(log_path))
